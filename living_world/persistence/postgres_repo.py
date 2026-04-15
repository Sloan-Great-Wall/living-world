"""PostgreSQL repository using psycopg3.

Import is deferred so the project still works without the `[db]` extra installed.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from living_world.core.agent import Agent, Item, LifeStage, Relationship
from living_world.core.event import LegendEvent
from living_world.core.tile import Tile
from living_world.core.world import World


class PostgresRepository:
    """Synchronous repo. Acceptable at Stage A QPS; async later if needed."""

    def __init__(self, dsn: str) -> None:
        try:
            import psycopg  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Install the db extra: pip install -e '.[db]' (needs psycopg[binary])"
            ) from exc
        import psycopg

        self._psycopg = psycopg
        self._conn = psycopg.connect(dsn, autocommit=True)

    # ---------- helpers ----------
    def _exec(self, sql: str, params: tuple | None = None) -> list[tuple]:
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            try:
                return cur.fetchall()
            except self._psycopg.ProgrammingError:
                return []

    # ---------- save whole world ----------
    def save_world(self, world: World) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE world_meta SET current_tick = %s, loaded_packs = %s, updated_at = NOW() WHERE id = 1",
                (world.current_tick, world.loaded_packs),
            )
        for tile in world.all_tiles():
            self.upsert_tile(tile)
        for agent in world.all_agents():
            self.upsert_agent(agent)
        # relationships
        with self._conn.cursor() as cur:
            for agent in world.all_agents():
                for rel in agent.relationships.values():
                    cur.execute(
                        """
                        INSERT INTO relationships (source_id, target_id, affinity, kind, last_interaction_tick)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (source_id, target_id) DO UPDATE
                          SET affinity = EXCLUDED.affinity,
                              kind = EXCLUDED.kind,
                              last_interaction_tick = EXCLUDED.last_interaction_tick
                        """,
                        (agent.agent_id, rel.target_id, rel.affinity, rel.kind, rel.last_interaction_tick),
                    )

    # ---------- targeted writes ----------
    def upsert_tile(self, tile: Tile) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tiles (tile_id, display_name, primary_pack, tile_type, description,
                                   allowed_packs, tension_bias, event_cooldowns, resident_agents)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (tile_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    primary_pack = EXCLUDED.primary_pack,
                    tile_type = EXCLUDED.tile_type,
                    description = EXCLUDED.description,
                    allowed_packs = EXCLUDED.allowed_packs,
                    tension_bias = EXCLUDED.tension_bias,
                    event_cooldowns = EXCLUDED.event_cooldowns,
                    resident_agents = EXCLUDED.resident_agents
                """,
                (
                    tile.tile_id, tile.display_name, tile.primary_pack, tile.tile_type,
                    tile.description, tile.allowed_packs, tile.tension_bias,
                    json.dumps(tile.event_cooldowns), tile.resident_agents,
                ),
            )

    def upsert_agent(self, agent: Agent) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agents (agent_id, pack_id, display_name, persona_card, is_historical_figure,
                                    attributes, alignment, tags, life_stage, age, current_tile,
                                    current_goal, inventory, state_extra, last_tick, created_at_tick)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
                ON CONFLICT (agent_id) DO UPDATE SET
                    pack_id = EXCLUDED.pack_id,
                    display_name = EXCLUDED.display_name,
                    persona_card = EXCLUDED.persona_card,
                    is_historical_figure = EXCLUDED.is_historical_figure,
                    attributes = EXCLUDED.attributes,
                    alignment = EXCLUDED.alignment,
                    tags = EXCLUDED.tags,
                    life_stage = EXCLUDED.life_stage,
                    age = EXCLUDED.age,
                    current_tile = EXCLUDED.current_tile,
                    current_goal = EXCLUDED.current_goal,
                    inventory = EXCLUDED.inventory,
                    state_extra = EXCLUDED.state_extra,
                    last_tick = EXCLUDED.last_tick,
                    updated_at = NOW()
                """,
                (
                    agent.agent_id, agent.pack_id, agent.display_name, agent.persona_card,
                    agent.is_historical_figure,
                    json.dumps(agent.attributes), agent.alignment, list(agent.tags),
                    agent.life_stage.value, agent.age, agent.current_tile or None,
                    agent.current_goal,
                    json.dumps([i.model_dump() for i in agent.inventory]),
                    json.dumps(agent.state_extra),
                    agent.last_tick, agent.created_at_tick,
                ),
            )

    def append_event(self, event: LegendEvent) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO events (event_id, tick, pack_id, tile_id, event_kind, participants,
                                    outcome, stat_changes, relationship_changes,
                                    template_rendering, enhanced_rendering, spotlight_rendering,
                                    importance, tier_used)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO NOTHING
                """,
                (
                    uuid.UUID(event.event_id), event.tick, event.pack_id, event.tile_id or None,
                    event.event_kind, event.participants, event.outcome,
                    json.dumps(event.stat_changes), json.dumps(event.relationship_changes),
                    event.template_rendering, event.enhanced_rendering, event.spotlight_rendering,
                    event.importance, event.tier_used,
                ),
            )

    def update_current_tick(self, tick: int) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE world_meta SET current_tick = %s, updated_at = NOW() WHERE id = 1",
                (tick,),
            )

    # ---------- load world ----------
    def load_world(self) -> World | None:
        rows = self._exec("SELECT current_tick, loaded_packs FROM world_meta WHERE id = 1")
        if not rows:
            return None
        current_tick, loaded_packs = rows[0]
        if current_tick == 0 and not loaded_packs:
            return None  # never saved

        world = World(current_tick=current_tick)
        for pid in loaded_packs:
            world.mark_pack_loaded(pid)

        # tiles
        for row in self._exec(
            "SELECT tile_id, display_name, primary_pack, tile_type, description, allowed_packs, "
            "tension_bias, event_cooldowns, resident_agents FROM tiles"
        ):
            world.add_tile(
                Tile(
                    tile_id=row[0], display_name=row[1], primary_pack=row[2], tile_type=row[3],
                    description=row[4] or "", allowed_packs=list(row[5]),
                    tension_bias=row[6], event_cooldowns=row[7] or {},
                    resident_agents=list(row[8]),
                )
            )

        # agents (without relationships first)
        agent_rows = self._exec(
            "SELECT agent_id, pack_id, display_name, persona_card, is_historical_figure, "
            "attributes, alignment, tags, life_stage, age, current_tile, current_goal, "
            "inventory, state_extra, last_tick, created_at_tick FROM agents"
        )
        for row in agent_rows:
            agent = Agent(
                agent_id=row[0], pack_id=row[1], display_name=row[2],
                persona_card=row[3] or "", is_historical_figure=bool(row[4]),
                attributes=row[5] or {}, alignment=row[6], tags=set(row[7] or []),
                life_stage=LifeStage(row[8]), age=row[9], current_tile=row[10] or "",
                current_goal=row[11],
                inventory=[Item(**i) for i in (row[12] or [])],
                state_extra=row[13] or {},
                last_tick=row[14], created_at_tick=row[15],
            )
            world.add_agent(agent)

        # relationships
        for src, tgt, aff, kind, last_t in self._exec(
            "SELECT source_id, target_id, affinity, kind, last_interaction_tick FROM relationships"
        ):
            a = world.get_agent(src)
            if a is not None:
                a.relationships[tgt] = Relationship(
                    target_id=tgt, affinity=aff, kind=kind, last_interaction_tick=last_t,
                )

        # events
        for row in self._exec(
            "SELECT event_id, tick, pack_id, tile_id, event_kind, participants, outcome, "
            "stat_changes, relationship_changes, template_rendering, enhanced_rendering, "
            "spotlight_rendering, importance, tier_used FROM events ORDER BY tick ASC, created_at ASC"
        ):
            world.record_event(
                LegendEvent(
                    event_id=str(row[0]), tick=row[1], pack_id=row[2], tile_id=row[3] or "",
                    event_kind=row[4], participants=list(row[5] or []), outcome=row[6],
                    stat_changes=row[7] or {}, relationship_changes=row[8] or [],
                    template_rendering=row[9] or "", enhanced_rendering=row[10],
                    spotlight_rendering=row[11], importance=row[12], tier_used=row[13],
                )
            )
        return world

    def list_events(self, *, since_tick: int = 0, pack_id: str | None = None, limit: int = 1000) -> list[LegendEvent]:
        where = "tick >= %s"
        params: list[Any] = [since_tick]
        if pack_id:
            where += " AND pack_id = %s"
            params.append(pack_id)
        rows = self._exec(
            f"SELECT event_id, tick, pack_id, tile_id, event_kind, participants, outcome, "
            f"stat_changes, relationship_changes, template_rendering, enhanced_rendering, "
            f"spotlight_rendering, importance, tier_used "
            f"FROM events WHERE {where} ORDER BY tick DESC LIMIT %s",
            tuple(params + [limit]),
        )
        return [
            LegendEvent(
                event_id=str(r[0]), tick=r[1], pack_id=r[2], tile_id=r[3] or "",
                event_kind=r[4], participants=list(r[5] or []), outcome=r[6],
                stat_changes=r[7] or {}, relationship_changes=r[8] or [],
                template_rendering=r[9] or "", enhanced_rendering=r[10],
                spotlight_rendering=r[11], importance=r[12], tier_used=r[13],
            )
            for r in rows
        ]

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
