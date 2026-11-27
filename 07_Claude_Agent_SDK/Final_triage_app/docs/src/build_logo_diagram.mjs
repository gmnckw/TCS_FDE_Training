// Generates the logo-based architecture diagram (SVG) for triage_app/README.md.
// Logo vectors (Claude, Python) come from Archify's bundled Simple Icons set.
// The Streamlit/file/shield icons are generic drawings, not brand logos.
// usage: node build_logo_diagram.mjs <out.svg>
import { writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const marks = (await import(pathToFileURL('C:/Users/vijay/.claude/skills/archify/renderers/shared/generated-brand-marks.mjs').href)).BRAND_MARKS;
const brand = (id) => marks.find((m) => m.id === id);

// Place a 24x24 brand logo at (x,y) with size s, in its own brand colour.
const logo = (id, x, y, s) => {
  const b = brand(id);
  return `<g transform="translate(${x} ${y}) scale(${s / 24})"><path d="${b.path}" fill="#${b.hex}"/></g>`;
};

const C = { ink: '#1f2937', sub: '#5b6472' };
const FONT = "'Segoe UI', Inter, Arial, sans-serif";
const MONO = "Consolas, 'Cascadia Mono', monospace";

// Generic icons drawn on a 64x64 grid.
const wrap = (x, y, s, col, inner) =>
  `<g transform="translate(${x} ${y}) scale(${s / 64})" fill="none" stroke="${col}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">${inner}</g>`;
const iconBrowser = (x, y, s, c) => wrap(x, y, s, c,
  `<rect x="4" y="8" width="56" height="48" rx="7"/><line x1="4" y1="22" x2="60" y2="22"/><circle cx="13" cy="15" r="1.5" fill="${c}"/><circle cx="20" cy="15" r="1.5" fill="${c}"/><circle cx="27" cy="15" r="1.5" fill="${c}"/><line x1="14" y1="33" x2="50" y2="33"/><line x1="14" y1="42" x2="40" y2="42"/>`);
const iconFile = (x, y, s, c) => wrap(x, y, s, c,
  `<path d="M14 5h26l14 14v38a3 3 0 0 1-3 3H14a3 3 0 0 1-3-3V8a3 3 0 0 1 3-3z"/><path d="M40 5v14h14"/><line x1="21" y1="33" x2="44" y2="33"/><line x1="21" y1="43" x2="44" y2="43"/>`);
const iconFolder = (x, y, s, c) => wrap(x, y, s, c,
  `<path d="M5 16a4 4 0 0 1 4-4h16l6 7h24a4 4 0 0 1 4 4v28a4 4 0 0 1-4 4H9a4 4 0 0 1-4-4z"/>`);
const iconShield = (x, y, s, c) => wrap(x, y, s, c,
  `<path d="M32 5l22 8v17c0 14-9 24-22 29C19 54 10 44 10 30V13z"/><path d="M22 32l8 8 13-15"/>`);
const iconCard = (x, y, s, c) => wrap(x, y, s, c,
  `<rect x="5" y="10" width="54" height="44" rx="7"/><rect x="12" y="18" width="14" height="8" rx="2"/><line x1="12" y1="35" x2="52" y2="35"/><line x1="12" y1="44" x2="40" y2="44"/>`);

const text = (x, y, s, size, weight = 400, fill = C.ink, anchor = 'start', mono = false) =>
  `<text x="${x}" y="${y}" font-size="${size}" font-weight="${weight}" fill="${fill}" text-anchor="${anchor}" font-family="${mono ? MONO : FONT}">${s}</text>`;

const card = (x, y, w, h, stroke, fill) =>
  `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="22" fill="${fill}" stroke="${stroke}" stroke-width="3" filter="url(#sh)"/>`;

const arrow = (d, col, label, lx, ly, { dash = false, w = 3.5 } = {}) =>
  `<path d="${d}" fill="none" stroke="${col}" stroke-width="${w}" ${dash ? 'stroke-dasharray="10 8"' : ''} marker-end="url(#ah-${col.slice(1)})"/>` +
  (label
    ? `<rect x="${lx - label.length * 4.4 - 10}" y="${ly - 17}" width="${label.length * 8.8 + 20}" height="26" rx="13" fill="#f7f8fa"/>` +
      text(lx, ly + 2, label, 15, 600, col, 'middle')
    : '');

const markers = ['475569', '059669', '7c3aed', 'e11d48'].map((c) =>
  `<marker id="ah-${c}" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="#${c}"/></marker>`).join('');

const badge = (x, y, label, col) =>
  `<rect x="${x}" y="${y}" width="${label.length * 8.2 + 22}" height="26" rx="13" fill="${col}22" stroke="${col}" stroke-width="1.5"/>` +
  text(x + 11, y + 18, label, 14, 700, col);

const tools = (x, y, list, col) => list.map((t, i) => text(x, y + i * 27, '• ' + t, 17, 500, col, 'start', true)).join('');

let s = `<svg xmlns="http://www.w3.org/2000/svg" width="2200" height="1210" viewBox="0 0 2200 1210">
<defs>${markers}<filter id="sh" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#0f172a" flood-opacity="0.10"/></filter></defs>
<rect width="2200" height="1210" fill="#f7f8fa"/>
${text(60, 62, 'Support Ticket Triage Assistant', 40, 700)}
${text(60, 96, 'Claude Agent SDK · sessions · external + in-process MCP · hooks', 19, 400, C.sub)}`;

// ---------- connectors (drawn first, under the cards) ----------
s += '<g transform="translate(0 90)">';
s += arrow('M2040 400 V40 H150 V400', '#7c3aed', 'follow-up questions resume the same session (sessions.json)', 1100, 40, { dash: true });
s += arrow('M260 510 H340', '#475569', 'save', 300, 480);
s += arrow('M150 620 V735 H590 V620 H640', '#059669', 'run triage', 370, 735);
s += arrow('M1100 250 H440 V400', '#475569', 'read · mark processed (stdio)', 770, 250);
s += arrow('M960 400 H1030 V300 H1100', '#059669', 'external MCP', 1030, 360);
s += arrow('M960 575 H1100', '#059669', 'in-process MCP', 1030, 548);
s += arrow('M1270 720 V790', '#475569', 'KB lookup', 1270, 760);
s += arrow('M1440 575 H1580', '#475569', 'save_triage', 1510, 548);
s += arrow('M1840 530 H1920', '#059669', 'show', 1880, 503);
s += arrow('M800 680 V790', '#7c3aed', 'every call', 800, 740, { dash: true });
s += arrow('M640 875 H540', '#e11d48', 'audit log', 590, 848, { dash: true });

// ---------- cards ----------
// Streamlit UI
s += card(40, 400, 220, 220, '#0891b2', '#e6f7fb') + iconBrowser(86, 425, 128, '#0891b2') +
  text(150, 585, 'Streamlit UI', 22, 700, C.ink, 'middle') + text(150, 608, 'ui.py', 16, 400, C.sub, 'middle', true);
// Inbox
s += card(340, 400, 200, 220, '#7c3aed', '#efe9fd') + iconFile(380, 425, 120, '#7c3aed') +
  text(440, 573, 'inbox/', 22, 700, C.ink, 'middle') + text(440, 596, 'TKT-2001.md', 16, 400, C.sub, 'middle', true) +
  badge(365, 634, 'requirement 1', '#7c3aed');
// Agent (large Claude logo)
s += card(640, 340, 320, 340, '#059669', '#e7f7ef') + logo('claude', 740, 362, 120) +
  text(800, 525, 'Agent loop', 28, 700, C.ink, 'middle') + text(800, 553, 'ClaudeSDKClient · agent.py', 17, 400, C.sub, 'middle', true) +
  text(800, 590, 'model: claude-haiku-5-5', 17, 600, '#059669', 'middle', true) +
  text(800, 620, 'resumable session id', 16, 400, C.sub, 'middle') + text(800, 644, 'saved in sessions.json', 16, 400, C.sub, 'middle', true);
// tickets MCP (external, Python logo)
s += card(1100, 100, 340, 270, '#ea580c', '#fff1e6') + logo('python', 1124, 122, 84) +
  text(1230, 150, 'tickets', 28, 700) + text(1230, 178, 'MCP server', 20, 600, '#ea580c') + text(1230, 202, 'external · stdio process', 16, 400, C.sub) +
  text(1124, 250, 'ticket_store_mcp.py', 16, 600, C.sub, 'start', true) + tools(1124, 285, ['list_pending_tickets', 'read_ticket', 'mark_processed'], '#9a3412');
// support MCP (in-process, Python logo)
s += card(1100, 430, 340, 290, '#ea580c', '#fff1e6') + logo('python', 1124, 452, 84) +
  text(1230, 480, 'support', 28, 700) + text(1230, 508, 'MCP server', 20, 600, '#ea580c') + text(1230, 532, 'in-process · tools.py', 16, 400, C.sub) +
  text(1124, 580, 'create_sdk_mcp_server', 16, 600, C.sub, 'start', true) + tools(1124, 615, ['search_kb', 'lookup_account', 'file_escalation', 'save_triage'], '#9a3412');
// shared data
s += card(1100, 790, 340, 170, '#7c3aed', '#efe9fd') + iconFolder(1124, 815, 96, '#7c3aed') +
  text(1240, 850, 'Shared data', 24, 700) + text(1240, 880, 'data/kb/*.md', 16, 400, C.sub, 'start', true) +
  text(1240, 904, 'data/accounts.json', 16, 400, C.sub, 'start', true) + text(1240, 928, 'data/routing_policy.md', 15, 400, C.sub, 'start', true);
// outbox
s += card(1580, 430, 260, 200, '#7c3aed', '#efe9fd') + iconFile(1604, 452, 96, '#7c3aed') +
  text(1720, 490, 'outbox/', 24, 700) + text(1720, 518, '+ processed/', 15, 400, C.sub, 'start', true) +
  text(1604, 585, 'TKT-2001.json', 16, 400, C.sub, 'start', true) + text(1604, 609, 'TKT-2001.reply.md', 16, 400, C.sub, 'start', true) +
  badge(1605, 396, 'requirement 2', '#7c3aed');
// result card
s += card(1920, 400, 240, 260, '#0891b2', '#e6f7fb') + iconCard(1968, 425, 128, '#0891b2') +
  text(2040, 592, 'Result card', 22, 700, C.ink, 'middle') + text(2040, 618, 'priority · category · queue', 14, 400, C.sub, 'middle') +
  text(2040, 640, 'escalation · draft reply', 14, 400, C.sub, 'middle');
// hooks
s += card(640, 790, 320, 170, '#e11d48', '#fdecef') + iconShield(662, 815, 96, '#e11d48') + logo('python', 906, 806, 38) +
  text(770, 850, 'Hooks', 26, 700) + text(770, 876, 'hooks.py · PreToolUse', 15, 400, C.sub, 'start', true) +
  text(662, 935, 'hard-stop guard on save_triage', 17, 600, '#e11d48');
// audit
s += card(340, 790, 200, 170, '#7c3aed', '#efe9fd') + iconFile(390, 806, 70, '#7c3aed') +
  text(440, 905, 'audit.jsonl', 20, 700, C.ink, 'middle') + text(440, 930, 'every tool call', 15, 400, C.sub, 'middle');

s += '</g>';
// legend
s += `${logo('claude', 60, 1120, 34)}${text(104, 1145, 'Claude (agent / model)', 18, 500, C.sub)}` +
  `${logo('python', 360, 1120, 34)}${text(404, 1145, 'Python modules (MCP servers, hooks)', 18, 500, C.sub)}` +
  text(790, 1145, 'Streamlit, file and shield icons are generic drawings, not brand logos.', 16, 400, C.sub);
s += '</svg>';
writeFileSync(process.argv[2], s);
console.log('wrote', process.argv[2], s.length, 'bytes');
