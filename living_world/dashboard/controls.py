"""World Controls — direct dev panel for inspecting + manipulating the sim.

Seven tabs:
  1. Agent Editor   — edit any agent's goal / tile / tags / attributes /
                      needs / emotions / motivations / beliefs / life_stage.
  2. Memory Inspector — browse an agent's full memory stream, test recall.
  3. Tile Inspector — see tile state, cooldowns, tension, residents,
                      recent events.
  4. Event Injector — hand-craft an event and push it through the pipeline.
  5. Emergent Trigger — force the LLM to invent an event on a chosen tile.
  6. Engine Stats   — narrator budget, conscience tally, storyteller
                      tensions per pack, HF registry, world totals.
  7. Mechanics      — read-only on/off status of every LLM path.

The panel mutates World directly. The tick loop does NOT advance here —
press **+N days** in the sidebar to let the sim react to your changes.
"""

from __future__ import annotations

import html as _html
import uuid

import streamlit as st

from living_world.core.agent import LifeStage
from living_world.core.event import LegendEvent
from living_world.core.world import World


def render_controls_page(world: World, engine) -> None:
    """Render the full World Controls page into the current Streamlit area."""
    st.markdown("<h1>World Controls</h1>", unsafe_allow_html=True)
    st.caption(
        "Direct manipulation of the world. All changes take effect immediately "
        "on the in-memory state. Press **+N days** in the sidebar to let the "
        "sim react to what you changed."
    )

    tabs = st.tabs([
        "Agent Editor", "Memory Inspector", "Tile Inspector",
        "Event Injector", "Emergent Trigger", "Engine Stats", "Mechanics",
    ])

    with tabs[0]:
        _render_agent_editor(world)
    with tabs[1]:
        _render_memory_inspector(world, engine)
    with tabs[2]:
        _render_tile_inspector(world, engine)
    with tabs[3]:
        _render_event_injector(world, engine)
    with tabs[4]:
        _render_emergent_trigger(world, engine)
    with tabs[5]:
        _render_engine_stats(engine, world)
    with tabs[6]:
        _render_mechanics_overview(engine)


# ─────────────────────────────────────────────────────────────────────────
# 1. Agent editor
# ─────────────────────────────────────────────────────────────────────────

def _render_agent_editor(world: World) -> None:
    agents = sorted(
        world.all_agents(),
        key=lambda a: (not a.is_alive(), not a.is_historical_figure, a.pack_id, a.display_name),
    )
    if not agents:
        st.info("No agents in the world yet.")
        return

    labels = {
        a.agent_id: (
            f"{'✝ ' if not a.is_alive() else ''}"
            f"{'★ ' if a.is_historical_figure else ''}"
            f"{a.display_name}  ·  {a.pack_id}"
        )
        for a in agents
    }
    ids = [a.agent_id for a in agents]
    picked_id = st.selectbox(
        "Agent",
        ids,
        format_func=lambda x: labels.get(x, x),
        key="ctrl_agent_picker",
    )
    agent = world.get_agent(picked_id)
    if agent is None:
        return

    st.markdown(
        f"<div style='margin:8px 0;color:#8a8f9c;font-size:12.5px'>"
        f"ID <span class='mono' style='color:#cfd4dc'>{agent.agent_id}</span> "
        f"· age {agent.age} · {agent.life_stage.value} · tile "
        f"<span class='mono' style='color:#cfd4dc'>{agent.current_tile or '—'}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )

    col_goal, col_tile = st.columns([2, 1])
    with col_goal:
        new_goal = st.text_input(
            "Current goal",
            value=agent.current_goal or "",
            key=f"ctrl_goal_{picked_id}",
        )
    with col_tile:
        tile_ids = [""] + sorted(t.tile_id for t in world.all_tiles())
        try:
            cur_idx = tile_ids.index(agent.current_tile or "")
        except ValueError:
            cur_idx = 0
        new_tile = st.selectbox(
            "Current tile",
            tile_ids,
            index=cur_idx,
            key=f"ctrl_tile_{picked_id}",
        )

    col_stage, col_age = st.columns(2)
    with col_stage:
        stages = [s.value for s in LifeStage]
        new_stage = st.selectbox(
            "Life stage",
            stages,
            index=stages.index(agent.life_stage.value),
            key=f"ctrl_stage_{picked_id}",
            help="Setting to 'deceased' kills the character.",
        )
    with col_age:
        new_age = st.number_input(
            "Age",
            min_value=0, max_value=500, value=int(agent.age), step=1,
            key=f"ctrl_age_{picked_id}",
        )

    # Tags
    all_tags_across_world = sorted({
        t for other in world.all_agents() for t in other.tags
    } | agent.tags)
    new_tags = st.multiselect(
        "Tags",
        options=all_tags_across_world,
        default=sorted(agent.tags),
        key=f"ctrl_tags_{picked_id}",
    )
    new_tag_input = st.text_input(
        "Add a new tag (hit Apply below to save)",
        value="",
        key=f"ctrl_newtag_{picked_id}",
    )

    # Attributes
    st.markdown("**Attributes**")
    attr_cols = st.columns(2)
    new_attrs: dict = dict(agent.attributes)
    keys_snapshot = list(agent.attributes.keys())
    for i, k in enumerate(keys_snapshot):
        with attr_cols[i % 2]:
            v = agent.attributes[k]
            if isinstance(v, (int, float)):
                new_attrs[k] = st.number_input(
                    k, value=float(v), step=1.0,
                    key=f"ctrl_attr_{picked_id}_{k}",
                )
            else:
                new_attrs[k] = st.text_input(
                    k, value=str(v),
                    key=f"ctrl_attr_{picked_id}_{k}",
                )

    # Needs (Maslow drives, 0-100)
    st.markdown("**Needs**  ·  *0 = none, 100 = max urgency*")
    needs = agent.get_needs()
    new_needs: dict = {}
    n_cols = st.columns(len(needs)) if needs else []
    for col, (k, v) in zip(n_cols, needs.items()):
        with col:
            new_needs[k] = st.number_input(
                k, min_value=0.0, max_value=100.0, value=float(v), step=5.0,
                key=f"ctrl_need_{picked_id}_{k}",
            )

    # Emotions (PAD-style, 0-100, decays toward baseline each tick)
    st.markdown("**Emotions**  ·  *decay each tick*")
    emotions = agent.get_emotions()
    new_emotions: dict = {}
    e_cols = st.columns(len(emotions)) if emotions else []
    for col, (k, v) in zip(e_cols, emotions.items()):
        with col:
            new_emotions[k] = st.number_input(
                k, min_value=0.0, max_value=100.0, value=float(v), step=5.0,
                key=f"ctrl_emo_{picked_id}_{k}",
            )

    # Motivations (LLM-driven free-text urges, 0-3 strings)
    st.markdown("**Motivations**  ·  *one per line, max 3*")
    motivations_text = st.text_area(
        "motivations", value="\n".join(agent.get_motivations()),
        label_visibility="collapsed",
        key=f"ctrl_mot_{picked_id}",
        height=68,
    )

    # Beliefs
    st.markdown("**Beliefs**")
    beliefs = agent.get_beliefs()
    new_beliefs: dict = {}
    if beliefs:
        for topic, belief in list(beliefs.items()):
            c1, c2, c3 = st.columns([1, 3, 0.5])
            with c1:
                k = st.text_input(
                    "topic", value=topic, label_visibility="collapsed",
                    key=f"ctrl_bk_{picked_id}_{topic}",
                )
            with c2:
                v = st.text_input(
                    "belief", value=belief, label_visibility="collapsed",
                    key=f"ctrl_bv_{picked_id}_{topic}",
                )
            with c3:
                keep = not st.checkbox("✕", key=f"ctrl_brm_{picked_id}_{topic}",
                                        help="Remove this belief")
            if keep and k and v:
                new_beliefs[k] = v
    else:
        st.caption("No beliefs yet — they form through events / dialogue.")
    add_k = st.text_input("New belief topic", key=f"ctrl_addk_{picked_id}")
    add_v = st.text_input("New belief text",  key=f"ctrl_addv_{picked_id}")

    st.markdown("---")
    c_apply, c_reset_b, c_kill = st.columns(3)
    with c_apply:
        if st.button("Apply changes", type="primary", key=f"ctrl_apply_{picked_id}"):
            agent.current_goal = new_goal or None
            if new_tile and new_tile != agent.current_tile:
                _relocate(world, agent, new_tile)
            agent.life_stage = LifeStage(new_stage)
            agent.age = int(new_age)
            agent.tags = set(new_tags)
            if new_tag_input.strip():
                agent.tags.add(new_tag_input.strip().lower())
            # Attributes (only updated rows the user touched)
            for k, v in new_attrs.items():
                agent.attributes[k] = v
            # Beliefs: replace with the edited dict plus the new entry
            agent.state_extra["beliefs"] = dict(new_beliefs)
            if add_k.strip() and add_v.strip():
                agent.state_extra["beliefs"][add_k.strip()] = add_v.strip()
            # Needs / emotions / motivations
            agent.state_extra["needs"] = {k: float(v) for k, v in new_needs.items()}
            agent.state_extra["emotions"] = {k: float(v) for k, v in new_emotions.items()}
            mots = [m.strip() for m in motivations_text.splitlines() if m.strip()][:3]
            if mots:
                agent.state_extra["motivations"] = mots
            else:
                agent.state_extra.pop("motivations", None)
            st.success(f"Updated {agent.display_name}.")
    with c_reset_b:
        if st.button("Clear all beliefs", key=f"ctrl_clearb_{picked_id}"):
            agent.state_extra.pop("beliefs", None)
            st.rerun()
    with c_kill:
        if st.button("⚰️ Kill instantly", key=f"ctrl_kill_{picked_id}",
                     disabled=not agent.is_alive()):
            _kill_agent(world, agent)
            st.warning(f"{agent.display_name} is dead.")
            st.rerun()



def _relocate(world: World, agent, to_tile_id: str) -> None:
    old_tile = world.get_tile(agent.current_tile) if agent.current_tile else None
    if old_tile and agent.agent_id in old_tile.resident_agents:
        old_tile.resident_agents.remove(agent.agent_id)
    agent.current_tile = to_tile_id
    new_tile = world.get_tile(to_tile_id)
    if new_tile is not None and agent.agent_id not in new_tile.resident_agents:
        new_tile.resident_agents.append(agent.agent_id)


def _kill_agent(world: World, agent) -> None:
    agent.life_stage = LifeStage.DECEASED
    tile = world.get_tile(agent.current_tile) if agent.current_tile else None
    if tile and agent.agent_id in tile.resident_agents:
        tile.resident_agents.remove(agent.agent_id)


# ─────────────────────────────────────────────────────────────────────────
# 2. Event injector
# ─────────────────────────────────────────────────────────────────────────

def _render_event_injector(world: World, engine) -> None:
    st.markdown(
        "Hand-craft an event, push it through the full pipeline "
        "(consequences, memory, beliefs). Useful for nudging specific stories."
    )
    tile_ids = sorted(t.tile_id for t in world.all_tiles())
    if not tile_ids:
        st.info("No tiles loaded.")
        return

    tile_id = st.selectbox("Tile", tile_ids, key="inj_tile")
    tile = world.get_tile(tile_id)
    residents = world.agents_in_tile(tile_id)

    kind = st.text_input("Event kind (free-form label)", value="custom-event", key="inj_kind")
    participants = st.multiselect(
        "Participants",
        options=[a.agent_id for a in residents],
        format_func=lambda aid: world.get_agent(aid).display_name if world.get_agent(aid) else aid,
        default=[a.agent_id for a in residents[:2]],
        key="inj_parts",
    )
    col_out, col_imp = st.columns(2)
    with col_out:
        outcome = st.selectbox("Outcome", ["success", "failure", "neutral"], key="inj_out")
    with col_imp:
        importance = st.slider("Importance", 0.0, 1.0, 0.5, 0.05, key="inj_imp")
    narrative = st.text_area(
        "Narrative (shown in the Chronicle as-is)",
        value=f"At {tile.display_name if tile else tile_id}, something happened.",
        key="inj_narr",
    )

    if st.button("Inject event", type="primary", key="inj_go",
                 disabled=not participants):
        evt = LegendEvent(
            event_id=str(uuid.uuid4()),
            tick=world.current_tick,
            pack_id=tile.primary_pack if tile else "scp",
            tile_id=tile_id,
            event_kind=kind.strip() or "custom-event",
            participants=participants,
            outcome=outcome,
            template_rendering=narrative.strip(),
            enhanced_rendering=narrative.strip(),
            importance=float(importance),
            tier_used=2,
            is_emergent=True,  # reuse the emergent skip-enhance flag
        )
        # Minimal stats stub so _process_event doesn't crash
        from living_world.tick_loop import TickStats
        stats = TickStats(tick=world.current_tick)
        engine._process_event(evt, stats)
        st.success(f"Injected: {kind} @ {tile_id}. Chronicle will show it.")


# ─────────────────────────────────────────────────────────────────────────
# 3. Emergent trigger
# ─────────────────────────────────────────────────────────────────────────

def _render_emergent_trigger(world: World, engine) -> None:
    if engine.emergent_proposer is None:
        st.warning(
            "Emergent event proposer is not enabled. Turn it on in Settings "
            "(Advanced LLM features → Emergent events)."
        )
        return

    st.markdown(
        "Force the LLM to invent a novel event RIGHT NOW on the tile of your choice. "
        "The proposer looks at who is present, their beliefs, and their feelings "
        "toward each other — then writes something grounded in that state."
    )

    from living_world.rules.heat import hot_tiles as _hot
    hot = _hot(world, limit=5)
    if hot:
        hot_labels = {
            t.tile_id: f"{t.display_name} · {len(world.agents_in_tile(t.tile_id))} here"
            for t in hot
        }
    else:
        hot_labels = {}

    tile_ids = sorted(t.tile_id for t in world.all_tiles())
    default_idx = tile_ids.index(hot[0].tile_id) if hot and hot[0].tile_id in tile_ids else 0
    tile_id = st.selectbox(
        "Tile",
        tile_ids,
        index=default_idx,
        format_func=lambda tid: hot_labels.get(tid, tid),
        key="em_tile",
    )
    if hot:
        st.caption(
            "🔥 Currently hottest tiles: "
            + ", ".join(f"{t.display_name}" for t in hot[:3])
        )

    if st.button("⚡ Trigger emergent event", type="primary", key="em_go"):
        tile = world.get_tile(tile_id)
        if tile is None:
            st.error("Tile not found.")
            return
        with st.spinner("LLM inventing the event..."):
            event = engine.emergent_proposer.propose(tile, world)
        if event is None:
            st.warning(
                "The LLM declined or its output couldn't be parsed. "
                "Try a tile with more agents or run it again."
            )
            return
        from living_world.tick_loop import TickStats
        stats = TickStats(tick=world.current_tick)
        engine._process_event(event, stats)
        st.success(f"✨ {event.event_kind} @ {event.tile_id}")
        st.markdown(f"> {event.best_rendering()}")


# ─────────────────────────────────────────────────────────────────────────
# 4. Mechanics overview
# ─────────────────────────────────────────────────────────────────────────

def _render_mechanics_overview(engine) -> None:
    st.markdown("Which mechanisms are active right now, read-only. "
                "To toggle them, use **Settings** in the sidebar.")
    rows = [
        ("Movement: goal keyword bonus",
         f"×{engine.movement.goal_bonus:.2f}", engine.movement.goal_bonus > 1.0),
        ("Movement: LLM advisor",
         "on" if engine.movement.llm_advisor is not None else "off",
         engine.movement.llm_advisor is not None),
        ("Consciousness layer",
         "on" if engine.consciousness is not None else "off",
         engine.consciousness is not None),
        ("Weekly planner",
         "on" if engine.agent_planner is not None else "off",
         engine.agent_planner is not None),
        ("Chronicler (说书人)",
         "on" if engine.chronicler is not None else "off",
         engine.chronicler is not None),
        ("Emergent events",
         "on" if engine.emergent_proposer is not None else "off",
         engine.emergent_proposer is not None),
        ("Conversation loop",
         "on" if engine.conversation_loop_enabled else "off",
         engine.conversation_loop_enabled),
        ("Subjective perception",
         f"on (≥{engine.perception_threshold:.2f})" if engine.perception is not None else "off",
         engine.perception is not None),
        ("Agent self-update",
         f"on (≥{engine.self_update_threshold:.2f})" if engine.self_update is not None else "off",
         engine.self_update is not None),
    ]
    for label, value, on in rows:
        dot = "🟢" if on else "⚪"
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;"
            f"padding:6px 0;border-bottom:1px solid #15171f'>"
            f"<span>{dot} {label}</span>"
            f"<span class='mono subtle'>{value}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )


# ─────────────────────────────────────────────────────────────────────────
# 5. Memory Inspector — see what an agent currently remembers + test recall
# ─────────────────────────────────────────────────────────────────────────

def _render_memory_inspector(world: World, engine) -> None:
    if engine.memory is None:
        st.warning("Memory store is disabled. Turn on **Agent memory** in Settings.")
        return

    st.markdown(
        "Browse an agent's full memory stream. Each entry is one event the "
        "agent participated in (or a periodic reflection / self-update note). "
        "Use the recall box at the bottom to test what an LLM-prompted "
        "`memory.recall(agent_id, query)` would return."
    )

    agents = sorted(world.all_agents(),
                    key=lambda a: (not a.is_historical_figure, a.pack_id, a.display_name))
    if not agents:
        st.info("No agents in the world yet.")
        return
    ids = [a.agent_id for a in agents]
    labels = {a.agent_id: f"{'★ ' if a.is_historical_figure else ''}{a.display_name}"
              for a in agents}
    aid = st.selectbox("Agent", ids, format_func=lambda x: labels.get(x, x),
                        key="mem_agent")

    # Backend exposes per-agent entries via internal store
    backend = getattr(engine.memory, "_backend", None)
    entries = []
    if backend is not None and hasattr(backend, "_entries"):
        entries = [e for e in backend._entries if e.agent_id == aid]

    st.markdown(
        f"**{len(entries)} memory entries**  ·  "
        f"Sorted newest first. `subjective` = LLM-rewritten POV. "
        f"`reflection` = self_update reflection. `raw` = objective rendering."
    )
    for e in reversed(entries[-50:]):
        kind_color = {"subjective": "#b091d1", "reflection": "#e8c56a", "raw": "#5a7fa3"}
        col = kind_color.get(e.kind, "#5a6270")
        st.markdown(
            f'<div style="margin-bottom:10px;padding:10px 14px;'
            f'border-left:2px solid {col};background:#0a0c14;border-radius:4px">'
            f'<div class="mono subtle" style="font-size:10.5px;margin-bottom:4px">'
            f'DAY {e.tick:03d} · <span style="color:{col}">{e.kind}</span> · '
            f'imp {e.importance:.2f}</div>'
            f'<div style="font-size:13px;color:#cfd4dc;line-height:1.5">'
            f'{_html.escape(e.doc)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Live recall test
    st.markdown("---")
    st.markdown("**Test recall**  ·  *what would `memory.recall()` return for a query?*")
    query = st.text_input("Query", key="mem_query", placeholder="e.g. 'Kondraki research'")
    top_k = st.slider("top_k", 1, 10, 3, key="mem_topk")
    if query.strip():
        try:
            results = engine.memory.recall(aid, query.strip(), top_k=top_k) or []
        except Exception as exc:
            st.error(f"Recall failed: {exc}")
            results = []
        if not results:
            st.info("No matches.")
        else:
            for i, e in enumerate(results, 1):
                st.markdown(
                    f"**{i}.** `day {e.tick:03d} · {e.kind} · imp {e.importance:.2f}`\n\n"
                    f"> {e.doc[:280]}"
                )


# ─────────────────────────────────────────────────────────────────────────
# 6. Tile Inspector — cooldowns, tension, residents, recent events per tile
# ─────────────────────────────────────────────────────────────────────────

def _render_tile_inspector(world: World, engine) -> None:
    tiles = sorted(world.all_tiles(), key=lambda t: (t.primary_pack, t.tile_id))
    if not tiles:
        st.info("No tiles loaded.")
        return
    tid = st.selectbox(
        "Tile",
        [t.tile_id for t in tiles],
        format_func=lambda x: (
            f"{world.get_tile(x).primary_pack} · {world.get_tile(x).display_name} "
            f"({len(world.agents_in_tile(x))} here)"
        ),
        key="tile_inspect_picker",
    )
    tile = world.get_tile(tid)
    if tile is None:
        return

    c1, c2, c3 = st.columns(3)
    c1.metric("Type", tile.tile_type)
    c2.metric("Pack", tile.primary_pack)
    c3.metric("Residents", len(world.agents_in_tile(tid)))

    if tile.description:
        st.markdown(f"*{_html.escape(tile.description)}*")

    st.markdown("---")
    cA, cB = st.columns(2)
    with cA:
        st.markdown("**Position + bounds**")
        st.code(f"x={tile.x:.1f} y={tile.y:.1f} radius={tile.radius:.1f}",
                 language="text")
        if tile.allowed_packs:
            st.markdown(f"**Allowed packs:** `{', '.join(tile.allowed_packs)}`")
        st.markdown(f"**Tension bias:** `{tile.tension_bias:.2f}`")

    with cB:
        st.markdown("**Live tension** (storyteller)")
        st_obj = engine.storytellers.get(tid)
        if st_obj is not None:
            cur = st_obj.tension.current()
            target = st_obj.config.tension_target
            st.code(
                f"current={cur:.2f}  target={target:.2f}\n"
                f"recent_days={st_obj.tension.recent_days}\n"
                f"personality={st_obj.config.personality}",
                language="text",
            )

    # Cooldowns currently in effect
    if tile.event_cooldowns:
        active_cd = {k: v for k, v in tile.event_cooldowns.items()
                     if v > world.current_tick}
        if active_cd:
            st.markdown("**Active cooldowns** (event won't re-fire until day):")
            st.code("\n".join(f"  {k:30s} until day {v}"
                              for k, v in sorted(active_cd.items(),
                                                  key=lambda x: x[1])),
                    language="text")
        else:
            st.caption("All cooldowns expired — any event eligible.")
    else:
        st.caption("No cooldowns recorded yet.")

    st.markdown("---")
    st.markdown("**Residents**")
    residents = world.agents_in_tile(tid)
    if not residents:
        st.caption("No one is currently here.")
    else:
        for a in residents:
            badge = "★ " if a.is_historical_figure else ""
            st.markdown(
                f"- {badge}**{a.display_name}** · "
                f"goal: *{a.current_goal or '(none)'}* · "
                f"pos ({a.x:.0f}, {a.y:.0f})"
            )

    st.markdown("---")
    st.markdown("**Recent events here** (last 10 in this tile)")
    recent = [e for e in world.events_since(1) if e.tile_id == tid][-10:]
    if not recent:
        st.caption("No events have happened here yet.")
    for e in reversed(recent):
        st.markdown(
            f"- `day {e.tick:03d}` **{e.event_kind}** ({e.outcome}, imp {e.importance:.2f})  \n"
            f"  {e.best_rendering()[:200]}"
        )


# ─────────────────────────────────────────────────────────────────────────
# 7. Engine Stats — narrator budget, conscience tally, HF registry, etc.
# ─────────────────────────────────────────────────────────────────────────

def _render_engine_stats(engine, world: World) -> None:
    st.markdown("Live counters from the engine + agent layers. Read-only.")

    # Narrator (LLM narrative budget + tier counts)
    st.markdown("### Narrator (LLM narrative)")
    n = engine.narrator
    c1, c2, c3 = st.columns(3)
    c1.metric("Tier 1 events (template)", n.stats.tier1)
    c2.metric("Tier 3 events (LLM)", n.stats.tier3)
    used = getattr(n.budget, "tokens_used", 0)
    cap = getattr(n.budget, "tokens_limit", 0)
    pct = (used / cap * 100.0) if cap else 0.0
    c3.metric("Tier-3 token budget", f"{used}/{cap}", f"{pct:.1f}% used")

    # Consciousness layer
    if engine.consciousness is not None:
        st.markdown("### Consciousness (LLM verdict on rule-proposed events)")
        cs = engine.consciousness
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Activations", cs.activations)
        c2.metric("Approvals", cs.approvals)
        c3.metric("Adjustments", cs.adjustments)
        c4.metric("Vetoes", cs.vetoes)
        st.caption(
            f"Activation chance {cs.activation_chance:.0%} · "
            f"importance ≥ {cs.importance_threshold:.2f}"
        )

    # Storyteller tensions per pack
    st.markdown("### Storyteller tension by pack")
    by_pack: dict = {}
    for tid, st_obj in engine.storytellers.items():
        tile = world.get_tile(tid)
        if tile is None:
            continue
        by_pack.setdefault(tile.primary_pack, []).append(
            (tile.display_name, st_obj.tension.current(), st_obj.config.tension_target)
        )
    for pack, rows in sorted(by_pack.items()):
        st.markdown(f"**{pack}** · {len(rows)} tiles")
        rows.sort(key=lambda r: -r[1])
        for name, cur, tgt in rows[:5]:
            arrow = "🔥" if cur > tgt + 0.1 else ("💤" if cur < tgt - 0.1 else "·")
            st.markdown(f"- {arrow} *{name}*: {cur:.2f} (target {tgt:.2f})")

    # Historical figures
    st.markdown("### Historical Figures registry")
    summary = engine.hf_registry.summary()
    if isinstance(summary, dict):
        c1, c2 = st.columns(2)
        c1.metric("Active HF", summary.get("active", 0))
        c2.metric("Demoted ever", summary.get("demoted", 0))

    # World totals
    st.markdown("### World")
    s = world.summary()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Day", s["tick"])
    c2.metric("Events", s["events_logged"])
    c3.metric("Alive agents", s["agents_alive"])
    c4.metric("Chapters", len(world.chapters))
