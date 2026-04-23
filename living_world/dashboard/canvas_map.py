"""Canvas world map — HTML5 Canvas rendered via streamlit.components.v1.html().

Replaces the old SVG grid map with a continuous-space, zoomable/pannable
world view. All rendering is pure JavaScript in a single HTML string —
no React, no Node, no build step. The host (app.py) embeds the returned
HTML inside a sized iframe via components.html(..., height=...).
"""

from __future__ import annotations

import json

from living_world.dashboard.map_view import PACK_THEMES


def render_canvas_map(world_state: dict, *, height: int = 700) -> str:
    """Return an HTML string with <canvas> + embedded JS for the world map.

    Args:
        world_state: Output of factory.build_world_state_json().
        height: Pixel height used inside the HTML body CSS (the outer iframe
            size is controlled by the components.html(height=...) call).
    """
    # Serialize pack themes for JS
    pack_themes_js = json.dumps(PACK_THEMES)
    state_js = json.dumps(world_state)

    # Emoji lookup table — built in Python with real Unicode, serialized for JS
    tag_emoji_list = [
        ["great-old-one", "\U0001F300"], ["outer-god", "\U0001F30C"], ["deity", "\u2696\uFE0F"],
        ["permanent_historical", "\U0001F451"], ["anomaly", "\u25C8"],
        ["demon", "\U0001F608"], ["ghost", "\u25D0"], ["fox-spirit", "\U0001F98A"],
        ["hybrid", "\U0001F41F"], ["mi-go", "\U0001F98B"], ["dreamer", "\u25CE"],
        ["monk", "\u534D"], ["cultist", "\U0001F56F"], ["ai", "\u25FE"],
        ["o5", "\u25C9"], ["elite", "\u2726"], ["field-agent", "\u25C7"],
        ["investigator", "\u25C6"], ["law-enforcement", "\u25C6"],
        ["psychologist", "\u270E"], ["antiquarian", "\u2767"], ["artist", "\u270E"],
        ["d-class", "\u25CD"], ["scholar", "\u2712"], ["academic", "\u2712"],
        ["researcher", "\u2697"], ["staff", "\u25E6"],
        ["scp", "\u25C9"], ["cthulhu", "\u2726"], ["liaozhai", "\u2756"],
    ]
    tag_emoji_js = json.dumps(tag_emoji_list, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ width: 100%; height: {height}px; overflow: hidden; background: #04050a; }}
  canvas {{ display: block; width: 100%; height: {height}px; cursor: grab; }}
  canvas.dragging {{ cursor: grabbing; }}
  #tooltip {{
    position: fixed; pointer-events: none; z-index: 100;
    background: rgba(10, 12, 20, 0.92);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 6px; padding: 8px 12px;
    font-family: Inter, -apple-system, sans-serif;
    font-size: 12px; color: #cfd4dc;
    max-width: 240px; display: none;
    box-shadow: 0 4px 16px rgba(0,0,0,0.5);
  }}
  #tooltip .tt-name {{
    font-weight: 600; font-size: 13px; color: #f2f4f8; margin-bottom: 3px;
  }}
  #tooltip .tt-goal {{
    font-size: 11px; color: #8a8f9c; line-height: 1.4;
  }}
  #tooltip .tt-hf {{
    font-size: 10px; color: #e8c56a; letter-spacing: 0.08em; margin-bottom: 2px;
  }}
</style>
</head>
<body>
<canvas id="worldmap"></canvas>
<div id="tooltip"></div>
<script>
(function() {{
  "use strict";

  const STATE = {state_js};
  const THEMES = {pack_themes_js};
  const canvas = document.getElementById('worldmap');
  const ctx = canvas.getContext('2d');
  const tooltip = document.getElementById('tooltip');

  // ── Retina support ──
  let dpr = window.devicePixelRatio || 1;
  function resize() {{
    dpr = window.devicePixelRatio || 1;
    canvas.width = canvas.clientWidth * dpr;
    canvas.height = canvas.clientHeight * dpr;
  }}
  resize();
  window.addEventListener('resize', resize);

  // ── Camera (zoom + pan) ──
  let camX = 0, camY = 0, camScale = 1.0;

  // Auto-fit: compute bounding box of all tiles and center camera
  if (STATE.tiles.length > 0) {{
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const t of STATE.tiles) {{
      minX = Math.min(minX, t.x - t.radius);
      minY = Math.min(minY, t.y - t.radius);
      maxX = Math.max(maxX, t.x + t.radius);
      maxY = Math.max(maxY, t.y + t.radius);
    }}
    const worldW = maxX - minX;
    const worldH = maxY - minY;
    const pad = 80;
    const scaleX = (canvas.clientWidth - pad * 2) / worldW;
    const scaleY = (canvas.clientHeight - pad * 2) / worldH;
    camScale = Math.min(scaleX, scaleY, 2.5);
    camX = -(minX + worldW / 2) * camScale + canvas.clientWidth / 2;
    camY = -(minY + worldH / 2) * camScale + canvas.clientHeight / 2;
  }}

  // ── Agent positions: jitter around tile center ──
  function hashStr(s) {{
    let h = 0;
    for (let i = 0; i < s.length; i++) {{
      h = ((h << 5) - h + s.charCodeAt(i)) | 0;
    }}
    return h;
  }}

  const tileMap = {{}};
  for (const t of STATE.tiles) tileMap[t.tile_id] = t;

  // Compute stable positions for agents within their tiles
  const agentPositions = {{}};
  for (const a of STATE.agents) {{
    const tile = tileMap[a.current_tile];
    if (!tile) {{ agentPositions[a.agent_id] = {{ x: a.x, y: a.y }}; continue; }}
    // If agent has non-zero coords, use them; otherwise jitter from tile center
    if (a.x !== 0 || a.y !== 0) {{
      agentPositions[a.agent_id] = {{ x: a.x, y: a.y }};
    }} else {{
      const h = hashStr(a.agent_id);
      const angle = ((h & 0xFFFF) / 0xFFFF) * Math.PI * 2;
      const dist = ((h >>> 16 & 0x7FFF) / 0x7FFF) * tile.radius * (a.is_historical_figure ? 0.35 : 0.6);
      agentPositions[a.agent_id] = {{
        x: tile.x + Math.cos(angle) * dist,
        y: tile.y + Math.sin(angle) * dist,
      }};
    }}
  }}

  // ── Target positions for animation (lerp) ──
  let currentPositions = {{}};
  for (const id in agentPositions) {{
    currentPositions[id] = {{ x: agentPositions[id].x, y: agentPositions[id].y }};
  }}

  // ── Emoji lookup (mirrors Python TAG_EMOJI_RULES) ──
  const TAG_EMOJI = {tag_emoji_js};
  function agentEmoji(tags) {{
    for (const [needle, emo] of TAG_EMOJI) {{
      if (tags.includes(needle)) return emo;
    }}
    return "\u25CF";
  }}

  // ── Hit-testing ──
  let hoveredAgent = null;
  const AGENT_RADIUS = 11;

  function worldToScreen(wx, wy) {{
    return [wx * camScale + camX, wy * camScale + camY];
  }}
  function screenToWorld(sx, sy) {{
    return [(sx - camX) / camScale, (sy - camY) / camScale];
  }}

  function hitTest(sx, sy) {{
    const [wx, wy] = screenToWorld(sx, sy);
    let closest = null, closestDist = Infinity;
    for (const a of STATE.agents) {{
      const pos = currentPositions[a.agent_id] || agentPositions[a.agent_id];
      const dx = pos.x - wx, dy = pos.y - wy;
      const dist = Math.sqrt(dx * dx + dy * dy);
      const hitR = AGENT_RADIUS / camScale + 4;
      if (dist < hitR && dist < closestDist) {{
        closest = a;
        closestDist = dist;
      }}
    }}
    return closest;
  }}

  // ── Drawing ──
  function draw() {{
    const w = canvas.width, h = canvas.height;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Layer 1: Background gradient
    const bg = ctx.createRadialGradient(w/(2*dpr), h/(3*dpr), 0, w/(2*dpr), h/(2*dpr), w/(1.5*dpr));
    bg.addColorStop(0, '#0a0c14');
    bg.addColorStop(1, '#04050a');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w/dpr, h/dpr);

    // Subtle pack-themed ambient glow
    for (const t of STATE.tiles) {{
      const th = THEMES[t.primary_pack] || THEMES['scp'];
      const [sx, sy] = worldToScreen(t.x, t.y);
      const sr = t.radius * camScale * 1.8;
      const glow = ctx.createRadialGradient(sx, sy, 0, sx, sy, sr);
      glow.addColorStop(0, th.accent + '0A');
      glow.addColorStop(1, 'transparent');
      ctx.fillStyle = glow;
      ctx.fillRect(sx - sr, sy - sr, sr * 2, sr * 2);
    }}

    // Layer 2: Pack region labels (group by pack, draw label above first tile)
    const packFirstTile = {{}};
    for (const t of STATE.tiles) {{
      if (!packFirstTile[t.primary_pack] || t.y < packFirstTile[t.primary_pack].y) {{
        packFirstTile[t.primary_pack] = t;
      }}
    }}
    for (const [packId, t] of Object.entries(packFirstTile)) {{
      const th = THEMES[packId] || THEMES['scp'];
      const [sx, sy] = worldToScreen(t.x, t.y - t.radius - 30);
      ctx.font = '600 ' + Math.max(10, 13 * camScale) + 'px "Space Grotesk", Inter, sans-serif';
      ctx.fillStyle = th.text;
      ctx.globalAlpha = 0.7;
      ctx.textAlign = 'left';
      ctx.fillText(th.emblem + '  ' + packId.toUpperCase(), sx - 40 * camScale, sy);
      ctx.globalAlpha = 1.0;
    }}

    // Layer 3: Tile regions — semi-transparent circles
    for (const t of STATE.tiles) {{
      const th = THEMES[t.primary_pack] || THEMES['scp'];
      const [sx, sy] = worldToScreen(t.x, t.y);
      const sr = t.radius * camScale;

      // Fill
      ctx.beginPath();
      ctx.arc(sx, sy, sr, 0, Math.PI * 2);
      ctx.fillStyle = th.floor + 'B0';
      ctx.fill();

      // Border
      ctx.strokeStyle = th.accent + '5A';
      ctx.lineWidth = 1.2;
      ctx.stroke();

      // Tile name
      const fontSize = Math.max(8, 11 * camScale);
      ctx.font = '500 ' + fontSize + 'px Inter, sans-serif';
      ctx.fillStyle = th.text;
      ctx.globalAlpha = 0.8;
      ctx.textAlign = 'center';
      ctx.fillText(t.display_name, sx, sy - sr + fontSize + 4);
      ctx.globalAlpha = 1.0;

      // Tile type (small)
      const fontSize2 = Math.max(6, 8 * camScale);
      ctx.font = '400 ' + fontSize2 + 'px "JetBrains Mono", monospace';
      ctx.fillStyle = '#5a6270';
      ctx.fillText(t.tile_type, sx, sy - sr + fontSize + fontSize2 + 6);
    }}

    // Layer 4: Agents
    for (const a of STATE.agents) {{
      const pos = currentPositions[a.agent_id] || agentPositions[a.agent_id];
      if (!pos) continue;
      const th = THEMES[a.pack_id] || THEMES['scp'];
      const [sx, sy] = worldToScreen(pos.x, pos.y);
      const r = AGENT_RADIUS * Math.min(camScale, 1.8);
      const isSelected = a.agent_id === STATE.selected_agent;
      const isHovered = hoveredAgent && hoveredAgent.agent_id === a.agent_id;

      // HF glow
      if (a.is_historical_figure) {{
        ctx.beginPath();
        ctx.arc(sx, sy, r * 1.8, 0, Math.PI * 2);
        ctx.fillStyle = th.glow + '18';
        ctx.fill();
      }}

      // Agent circle
      ctx.beginPath();
      ctx.arc(sx, sy, r, 0, Math.PI * 2);
      ctx.fillStyle = th.floor_light || th.floor;
      ctx.fill();

      // Border
      if (isSelected) {{
        ctx.strokeStyle = '#e8c56a';
        ctx.lineWidth = 2.5;
        ctx.stroke();
        // Selection ring
        ctx.beginPath();
        ctx.arc(sx, sy, r + 4, 0, Math.PI * 2);
        ctx.strokeStyle = '#e8c56a44';
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }} else if (isHovered) {{
        ctx.strokeStyle = th.glow;
        ctx.lineWidth = 2;
        ctx.stroke();
      }} else {{
        ctx.strokeStyle = th.accent;
        ctx.lineWidth = 1;
        ctx.stroke();
      }}

      // Emoji
      const emoSize = Math.max(8, 12 * Math.min(camScale, 1.5));
      ctx.font = emoSize + 'px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = th.text;
      ctx.fillText(agentEmoji(a.tags), sx, sy + 1);
      ctx.textBaseline = 'alphabetic';

      // Layer 5: Agent name label
      if (camScale > 0.5) {{
        const nameSize = Math.max(6, 8.5 * Math.min(camScale, 1.3));
        ctx.font = '500 ' + nameSize + 'px Inter, sans-serif';
        ctx.fillStyle = th.text;
        ctx.globalAlpha = isSelected || isHovered ? 1.0 : 0.7;
        ctx.textAlign = 'center';
        const name = a.display_name.length > 12 ? a.display_name.slice(0, 11) + '\u2026' : a.display_name;
        ctx.fillText(name, sx, sy + r + nameSize + 3);
        ctx.globalAlpha = 1.0;
      }}
    }}

    // Layer 6: Event flash particles (recent events in last 2 ticks)
    const recentTick = STATE.tick;
    for (const evt of STATE.recent_events) {{
      if (evt.tick >= recentTick - 1) {{
        const tile = tileMap[evt.pack_id];  // find any tile for this event
        // Find tile by checking participants
        for (const a of STATE.agents) {{
          if (evt.participants.includes(a.agent_id)) {{
            const pos = currentPositions[a.agent_id] || agentPositions[a.agent_id];
            if (pos) {{
              const [sx, sy] = worldToScreen(pos.x, pos.y);
              const th = THEMES[evt.pack_id] || THEMES['scp'];
              const age = recentTick - evt.tick;
              const alpha = Math.max(0.05, 0.3 - age * 0.15);
              ctx.beginPath();
              ctx.arc(sx, sy, (20 + age * 15) * camScale, 0, Math.PI * 2);
              ctx.strokeStyle = th.glow;
              ctx.globalAlpha = alpha;
              ctx.lineWidth = 1.5;
              ctx.stroke();
              ctx.globalAlpha = 1.0;
            }}
            break;
          }}
        }}
      }}
    }}
  }}

  // ── Mouse interaction ──
  let isDragging = false, dragStartX = 0, dragStartY = 0, camStartX = 0, camStartY = 0;

  canvas.addEventListener('mousedown', (e) => {{
    isDragging = true;
    dragStartX = e.clientX;
    dragStartY = e.clientY;
    camStartX = camX;
    camStartY = camY;
    canvas.classList.add('dragging');
  }});

  canvas.addEventListener('mousemove', (e) => {{
    if (isDragging) {{
      camX = camStartX + (e.clientX - dragStartX);
      camY = camStartY + (e.clientY - dragStartY);
      requestAnimationFrame(draw);
      return;
    }}
    // Hover hit test
    const prev = hoveredAgent;
    hoveredAgent = hitTest(e.clientX, e.clientY);
    if (hoveredAgent !== prev) requestAnimationFrame(draw);

    if (hoveredAgent) {{
      canvas.style.cursor = 'pointer';
      const th = THEMES[hoveredAgent.pack_id] || THEMES['scp'];
      let html = '';
      if (hoveredAgent.is_historical_figure) {{
        html += '<div class="tt-hf">\u2605 HISTORICAL FIGURE</div>';
      }}
      html += '<div class="tt-name">' + hoveredAgent.display_name + '</div>';
      if (hoveredAgent.current_goal) {{
        html += '<div class="tt-goal">' + hoveredAgent.current_goal + '</div>';
      }}
      html += '<div class="tt-goal" style="margin-top:3px;color:#5a6270">'
        + hoveredAgent.life_stage + ' \u00b7 age ' + hoveredAgent.age
        + ' \u00b7 ' + (tileMap[hoveredAgent.current_tile]?.display_name || hoveredAgent.current_tile)
        + '</div>';
      tooltip.innerHTML = html;
      tooltip.style.display = 'block';
      tooltip.style.left = (e.clientX + 14) + 'px';
      tooltip.style.top = (e.clientY - 10) + 'px';
      // Keep tooltip in viewport
      const rect = tooltip.getBoundingClientRect();
      if (rect.right > window.innerWidth) {{
        tooltip.style.left = (e.clientX - rect.width - 10) + 'px';
      }}
      if (rect.bottom > window.innerHeight) {{
        tooltip.style.top = (e.clientY - rect.height - 10) + 'px';
      }}
    }} else {{
      canvas.style.cursor = 'grab';
      tooltip.style.display = 'none';
    }}
  }});

  canvas.addEventListener('mouseup', () => {{
    isDragging = false;
    canvas.classList.remove('dragging');
  }});

  canvas.addEventListener('mouseleave', () => {{
    isDragging = false;
    canvas.classList.remove('dragging');
    hoveredAgent = null;
    tooltip.style.display = 'none';
    requestAnimationFrame(draw);
  }});

  // Zoom
  canvas.addEventListener('wheel', (e) => {{
    e.preventDefault();
    const zoomFactor = e.deltaY < 0 ? 1.12 : 1 / 1.12;
    const mx = e.clientX, my = e.clientY;
    // Zoom toward mouse position
    camX = mx - (mx - camX) * zoomFactor;
    camY = my - (my - camY) * zoomFactor;
    camScale *= zoomFactor;
    camScale = Math.max(0.15, Math.min(6.0, camScale));
    requestAnimationFrame(draw);
  }}, {{ passive: false }});

  // ── Animation loop for lerp ──
  const LERP_SPEED = 0.08;
  let animating = false;

  function animatePositions() {{
    let needsMore = false;
    for (const id in agentPositions) {{
      const target = agentPositions[id];
      const cur = currentPositions[id];
      if (!cur) {{ currentPositions[id] = {{ x: target.x, y: target.y }}; continue; }}
      const dx = target.x - cur.x, dy = target.y - cur.y;
      if (Math.abs(dx) > 0.1 || Math.abs(dy) > 0.1) {{
        cur.x += dx * LERP_SPEED;
        cur.y += dy * LERP_SPEED;
        needsMore = true;
      }} else {{
        cur.x = target.x;
        cur.y = target.y;
      }}
    }}
    draw();
    if (needsMore) {{
      requestAnimationFrame(animatePositions);
    }} else {{
      animating = false;
    }}
  }}

  // Initial draw
  draw();

  // Start lerp animation
  if (!animating) {{
    animating = true;
    requestAnimationFrame(animatePositions);
  }}

}})();
</script>
</body>
</html>"""
