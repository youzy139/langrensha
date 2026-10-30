// 月下狼人杀 · 手绘 SVG 美术：角色牌、玩家头像、村庄场景、篝火。
// 全部是内联 SVG 字符串，不依赖任何外部图片；颜色尽量走 CSS 变量，昼夜切换时跟着变。
"use strict";

const ART = (() => {
  // 四角星（闪光）
  const spark = (x, y, r, c = "#fff", o = 1) =>
    `<path d="M${x} ${y - r}Q${x} ${y} ${x + r} ${y}Q${x} ${y} ${x} ${y + r}Q${x} ${y} ${x - r} ${y}Q${x} ${y} ${x} ${y - r}Z" fill="${c}" opacity="${o}"/>`;
  const stars = (list, c) => list.map(([x, y, r, o]) => spark(x, y, r, c, o)).join("");
  const svg = (body, cls = "art") =>
    `<svg class="${cls}" viewBox="0 0 200 280" preserveAspectRatio="xMidYMid slice">${body}</svg>`;
  const bg = (id, c1, c2, cy = "40%") =>
    `<defs><radialGradient id="${id}" cx="50%" cy="${cy}" r="75%"><stop offset="0" stop-color="${c1}"/>` +
    `<stop offset="1" stop-color="${c2}"/></radialGradient></defs><rect width="200" height="280" fill="url(#${id})"/>`;
  const blur = id => `<filter id="${id}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4"/></filter>`;

  // ---------- 狼人：满月前的低多边形狼首 ----------
  const werewolf = () => svg(`${bg("aw-bg", "#5b1f35", "#12081a")}<defs>${blur("aw-gl")}</defs>
    ${stars([[24, 30, 4, .7], [170, 40, 3, .6], [150, 250, 3, .3], [30, 200, 2.5, .4]], "#ffd7de")}
    <circle cx="100" cy="112" r="80" fill="#f6e3b5" opacity=".1"/>
    <circle cx="100" cy="112" r="62" fill="#f6e3b5" opacity=".92"/>
    <circle cx="80" cy="96" r="9" fill="#e7cf98" opacity=".7"/><circle cx="122" cy="128" r="6" fill="#e7cf98" opacity=".6"/>
    <polygon points="100,224 70,190 56,152 50,112 38,50 80,92 100,86 120,92 162,50 150,112 144,152 130,190" fill="#30344b"/>
    <polygon points="100,224 70,190 56,152 50,112 38,50 80,92 100,86" fill="#222538"/>
    <polygon points="80,92 100,86 120,92 100,130" fill="#3d4260"/>
    <polygon points="44,64 60,104 76,94" fill="#7a2c44"/><polygon points="156,64 140,104 124,94" fill="#7a2c44"/>
    <polygon points="56,152 78,150 70,190" fill="#1b1d2c"/><polygon points="144,152 122,150 130,190" fill="#3a3e58"/>
    <polygon points="100,140 84,158 88,198 100,214 112,198 116,158" fill="#4c5272"/>
    <polygon points="100,140 84,158 88,198 100,214" fill="#41465f"/>
    <g filter="url(#aw-gl)"><polygon points="62,130 90,138 82,150 64,142" fill="#ff2d55"/><polygon points="138,130 110,138 118,150 136,142" fill="#ff2d55"/></g>
    <polygon points="64,132 88,139 82,148 66,142" fill="#ff5a77"/><polygon points="136,132 112,139 118,148 134,142" fill="#ff5a77"/>
    <path d="M77 136 L76 146 M123 136 L124 146" stroke="#2a0a12" stroke-width="2.4"/>
    <polygon points="89,186 111,186 100,199" fill="#0b0c14"/>
    <path d="M100 199 L100 207 M90 208 Q100 216 110 208" stroke="#0b0c14" stroke-width="2" fill="none"/>
    <polygon points="91,207 94,220 98,208" fill="#f3eee2"/><polygon points="102,208 106,220 109,207" fill="#f3eee2"/>
    <path d="M150 232 L170 262 M160 228 L182 256 M140 238 L158 268" stroke="#ff4d6d" stroke-width="3" stroke-linecap="round" opacity=".45"/>`);

  // ---------- 预言家：兜帽身影与水晶球 ----------
  const seer = () => svg(`${bg("as-bg", "#3d2c7d", "#0b0821", "72%")}<defs>${blur("as-gl")}
    <radialGradient id="as-ball" cx="38%" cy="32%" r="70%"><stop offset="0" stop-color="#f4ecff"/>
    <stop offset=".35" stop-color="#ad90ff"/><stop offset="1" stop-color="#33247d"/></radialGradient></defs>
    ${stars([[30, 40, 5, .9], [168, 60, 4, .8], [150, 24, 2.5, .6], [40, 120, 3, .5], [176, 150, 3, .5], [22, 236, 2.5, .4]], "#e2d6ff")}
    <path d="M26 280 L50 150 Q58 66 100 58 Q142 66 150 150 L174 280 Z" fill="#1c1540"/>
    <path d="M100 58 Q142 66 150 150 L174 280 L100 280Z" fill="#251c52"/>
    <ellipse cx="100" cy="126" rx="29" ry="35" fill="#06041a"/>
    <path d="M86 70 Q100 62 114 70" stroke="#c9a35a" stroke-width="2" fill="none"/>
    <path d="M97 64 a6 6 0 1 0 6 8 a5 5 0 1 1 -6 -8Z" fill="#f2c46d"/>
    <ellipse cx="89" cy="125" rx="4.5" ry="2.4" fill="#d9ccff"/><ellipse cx="111" cy="125" rx="4.5" ry="2.4" fill="#d9ccff"/>
    <circle cx="100" cy="212" r="54" fill="#9d7bff" opacity=".35" filter="url(#as-gl)"/>
    <circle cx="100" cy="212" r="37" fill="url(#as-ball)"/>
    <path d="M77 212 Q100 193 123 212 Q100 231 77 212Z" fill="#1c1540" opacity=".72"/>
    <circle cx="100" cy="212" r="8" fill="#efe6ff"/><circle cx="100" cy="212" r="3.4" fill="#1c1540"/>
    <ellipse cx="88" cy="196" rx="9" ry="5" fill="#fff" opacity=".35" transform="rotate(-30 88 196)"/>
    <path d="M76 246 L124 246 L116 262 L84 262Z" fill="#c9a35a"/><rect x="72" y="260" width="56" height="7" rx="2" fill="#a07f3c"/>`);

  // ---------- 女巫：尖帽 + 解药 / 毒药 ----------
  const witch = () => svg(`${bg("ah-bg", "#1f4a37", "#07120d", "60%")}<defs>${blur("ah-gl")}</defs>
    ${stars([[28, 36, 4, .7], [60, 18, 2.5, .5], [176, 120, 3, .4]], "#d8ffe9")}
    <path d="M160 26 a20 20 0 1 0 14 34 a16 16 0 1 1 -14 -34Z" fill="#f6e3b5" opacity=".85"/>
    <path d="M54 150 L98 42 Q108 20 128 30 Q142 38 138 52 Q124 42 116 54 L148 150Z" fill="#2a1d42"/>
    <path d="M98 42 Q108 20 128 30 Q142 38 138 52 Q124 42 116 54 L148 150 L100 150Z" fill="#33244f"/>
    <path d="M63 126 L139 126 L145 147 L57 147Z" fill="#7b3fb0"/>
    <rect x="90" y="128" width="20" height="16" rx="2" fill="none" stroke="#f2c46d" stroke-width="3"/>
    <ellipse cx="100" cy="150" rx="80" ry="14" fill="#1b1330"/>
    <path d="M64 156 Q100 214 136 156Z" fill="#090611"/>
    <g filter="url(#ah-gl)"><circle cx="88" cy="170" r="5" fill="#5dff9e"/><circle cx="112" cy="170" r="5" fill="#5dff9e"/></g>
    <ellipse cx="88" cy="170" rx="4" ry="2.6" fill="#b8ffd4"/><ellipse cx="112" cy="170" rx="4" ry="2.6" fill="#b8ffd4"/>
    <path d="M86 184 Q100 194 114 184" stroke="#5dff9e" stroke-width="2" fill="none" opacity=".8"/>
    <circle cx="62" cy="236" r="30" fill="#2ecc71" opacity=".35" filter="url(#ah-gl)"/>
    <rect x="55" y="196" width="14" height="16" fill="#cfe9dc" opacity=".55"/><rect x="53" y="189" width="18" height="8" rx="2" fill="#8a5a2b"/>
    <circle cx="62" cy="234" r="25" fill="#27b765"/><path d="M38 236 Q62 226 86 236 A25 25 0 0 1 38 236Z" fill="#1e9653"/>
    <ellipse cx="53" cy="224" rx="6" ry="4" fill="#fff" opacity=".4"/>
    <circle cx="140" cy="236" r="30" fill="#9b59b6" opacity=".35" filter="url(#ah-gl)"/>
    <rect x="133" y="190" width="14" height="18" fill="#e6d4f0" opacity=".5"/><rect x="131" y="183" width="18" height="8" rx="2" fill="#8a5a2b"/>
    <path d="M124 208 L156 208 L162 264 L118 264Z" fill="#8e44ad"/>
    <circle cx="140" cy="232" r="8" fill="#f2e8fa"/><rect x="135" y="237" width="10" height="6" rx="1" fill="#f2e8fa"/>
    <circle cx="137" cy="231" r="2" fill="#4a1d5e"/><circle cx="143" cy="231" r="2" fill="#4a1d5e"/>
    <g class="bubbles"><circle cx="60" cy="182" r="3" fill="#7dffb0" opacity=".7"/><circle cx="68" cy="170" r="2" fill="#7dffb0" opacity=".5"/>
    <circle cx="142" cy="172" r="2.5" fill="#d7a6ff" opacity=".6"/></g>`);
  // ---------- 猎人：宽檐帽 + 猎枪准星 ----------
  const hunter = () => svg(`${bg("ar-bg", "#6b3b14", "#160b04", "45%")}<defs>${blur("ar-gl")}</defs>
    ${stars([[30, 30, 3, .5], [172, 46, 3, .5]], "#ffe1b8")}
    <circle cx="100" cy="128" r="74" fill="none" stroke="#f2c46d" stroke-width="2" opacity=".35"/>
    <circle cx="100" cy="128" r="56" fill="none" stroke="#f2c46d" stroke-width="1" opacity=".3" stroke-dasharray="4 6"/>
    <path d="M100 42 L100 64 M100 192 L100 214 M14 128 L36 128 M164 128 L186 128" stroke="#f2c46d" stroke-width="2" opacity=".45"/>
    <path d="M46 280 Q48 210 100 200 Q152 210 154 280Z" fill="#4a2b14"/>
    <path d="M78 206 L100 238 L122 206" fill="#2b190b"/>
    <path d="M74 204 L94 280 M126 204 L106 280" stroke="#8b5a2b" stroke-width="5"/>
    <rect x="80" y="150" width="40" height="52" rx="8" fill="#c48a5a"/>
    <path d="M80 176 Q100 214 120 176 L120 196 Q100 212 80 196Z" fill="#5a3618"/>
    <path d="M84 166 L96 168 M104 168 L116 166" stroke="#2b190b" stroke-width="3" stroke-linecap="round"/>
    <circle cx="91" cy="172" r="2.4" fill="#1a0f06"/><circle cx="109" cy="172" r="2.4" fill="#1a0f06"/>
    <ellipse cx="100" cy="150" rx="64" ry="12" fill="#3a2410"/>
    <path d="M70 148 Q70 100 100 98 Q130 100 130 148Z" fill="#5a3618"/>
    <path d="M70 140 L130 140 L130 148 L70 148Z" fill="#a8742f"/>
    <path d="M128 132 Q150 106 142 92 Q136 110 124 124Z" fill="#c0392b"/>
    <g transform="rotate(-32 100 236)">
      <rect x="20" y="230" width="140" height="8" rx="3" fill="#2a2a2e"/>
      <rect x="20" y="228" width="12" height="12" rx="2" fill="#1a1a1e"/>
      <path d="M120 230 L176 226 L182 246 L128 242Z" fill="#7a4a1e"/>
    </g>
    <circle cx="36" cy="214" r="10" fill="#ffb347" opacity=".9" filter="url(#ar-gl)"/>`);

  // ---------- 平民：提灯与小屋 ----------
  const villager = () => svg(`${bg("av-bg", "#26406e", "#0a1222", "38%")}<defs>${blur("av-gl")}</defs>
    ${stars([[24, 28, 3.5, .8], [60, 54, 2.5, .6], [150, 30, 3, .7], [180, 80, 2, .5]], "#e4ecff")}
    <path d="M150 54 a18 18 0 1 0 12 30 a14 14 0 1 1 -12 -30Z" fill="#f6e3b5" opacity=".85"/>
    <path d="M0 190 Q50 168 100 182 Q150 196 200 176 L200 280 L0 280Z" fill="#152340"/>
    <path d="M14 196 L14 160 L36 140 L58 160 L58 196Z" fill="#1d2c4f"/><path d="M8 164 L36 136 L64 164" fill="#2b1a1a"/>
    <rect x="30" y="172" width="10" height="12" fill="#ffd27a" opacity=".85"/>
    <path d="M148 192 L148 166 L166 150 L184 166 L184 192Z" fill="#1d2c4f"/><path d="M142 170 L166 146 L190 170" fill="#2b1a1a"/>
    <rect x="160" y="174" width="9" height="10" fill="#ffd27a" opacity=".7"/>
    <path d="M58 280 Q58 200 100 192 Q142 200 142 280Z" fill="#6b4a2b"/>
    <path d="M58 280 Q58 200 100 192 L100 280Z" fill="#5b3d22"/>
    <rect x="96" y="214" width="8" height="66" fill="#3e2a16"/>
    <circle cx="100" cy="158" r="30" fill="#e8b48a"/>
    <path d="M70 152 Q72 122 100 120 Q128 122 130 152 Q118 136 100 138 Q82 136 70 152Z" fill="#6e4523"/>
    <circle cx="90" cy="160" r="3" fill="#2a1a0e"/><circle cx="110" cy="160" r="3" fill="#2a1a0e"/>
    <path d="M90 172 Q100 179 110 172" stroke="#2a1a0e" stroke-width="2.4" fill="none" stroke-linecap="round"/>
    <circle cx="82" cy="168" r="4" fill="#ff9f8a" opacity=".55"/><circle cx="118" cy="168" r="4" fill="#ff9f8a" opacity=".55"/>
    <path d="M138 200 L138 222" stroke="#3e2a16" stroke-width="2"/>
    <circle cx="138" cy="238" r="28" fill="#ffc44d" opacity=".45" filter="url(#av-gl)"/>
    <path d="M128 224 L148 224 L150 252 L126 252Z" fill="#3a2a1a"/>
    <rect x="130" y="228" width="16" height="20" fill="#ffd27a"/><path d="M138 232 q-4 6 0 12 q4 -6 0 -12Z" fill="#ff8c1a"/>
    <path d="M124 222 L152 222 L148 216 L128 216Z" fill="#2a1d10"/>`);

  // ---------- 牌背：未知身份 ----------
  const back = () => svg(`${bg("ab-bg", "#2b2350", "#0b0a1a")}
    <rect x="12" y="12" width="176" height="256" rx="12" fill="none" stroke="#f2c46d" stroke-width="2" opacity=".5"/>
    <rect x="20" y="20" width="160" height="240" rx="8" fill="none" stroke="#f2c46d" stroke-width="1" opacity=".3"/>
    <circle cx="100" cy="140" r="54" fill="none" stroke="#f2c46d" stroke-width="2" opacity=".6"/>
    <path d="M100 96 a44 44 0 1 0 30 76 a36 36 0 1 1 -30 -76Z" fill="#f2c46d" opacity=".85"/>
    ${stars([[132, 110, 6, .9], [66, 186, 4, .6], [100, 40, 5, .5], [100, 240, 5, .5]], "#f2c46d")}`);

  const ROLE_ART = { werewolf, seer, witch, hunter, villager, back };
  const card = role => (ROLE_ART[role] || back)();

  // ---------- 玩家头像：按名字生成的村民肖像（同名永远同一张脸） ----------
  function hash(str) {
    let h = 2166136261;
    for (const ch of str) h = Math.imul(h ^ ch.codePointAt(0), 16777619);
    return h >>> 0;
  }
  const SKIN = ["#f1c7a5", "#e8b48a", "#d39a6a", "#b97c4f", "#f5d6bd", "#8d5a3b"];
  const HAIR = ["#2b1a10", "#5a3618", "#a0522d", "#d9a441", "#1c1c28", "#7a2c44", "#c7c2b8", "#3a4a7a"];
  const CLOTH = ["#3a4a7a", "#6b3b5a", "#2f5d50", "#7a4a1e", "#4b3a7a", "#8a2f3a", "#2d4f6b", "#5a5a2e"];
  const HAIRS = [
    c => `<path d="M14 30 Q14 10 32 10 Q50 10 50 30 Q44 18 32 19 Q20 18 14 30Z" fill="${c}"/>`,
    c => `<path d="M12 36 Q10 8 32 8 Q54 8 52 36 L48 26 Q40 16 32 17 Q22 16 16 26Z" fill="${c}"/>`,
    c => `<path d="M14 28 Q16 9 32 9 Q48 9 50 28 Q40 22 30 14 Q24 22 14 28Z" fill="${c}"/>`,
    c => `<path d="M10 52 Q6 10 32 8 Q58 10 54 52 Q50 30 46 22 Q32 14 18 22 Q14 30 10 52Z" fill="${c}"/>`,
    c => `<path d="M14 30 Q14 12 32 11 Q50 12 50 30 Q46 22 32 22 Q18 22 14 30Z" fill="${c}"/><circle cx="32" cy="8" r="6" fill="${c}"/>`,
    c => `<path d="M14 28 Q12 12 32 10 Q52 12 50 28Z" fill="${c}"/><path d="M8 28 L56 28 L50 22 L14 22Z" fill="#3a2410"/>`,
  ];
  const HATS = [
    "",
    `<path d="M6 25 L58 25 L52 20 L12 20Z" fill="#3a2410"/><path d="M16 21 Q18 4 32 4 Q46 4 48 21Z" fill="#5a3618"/><rect x="16" y="16" width="32" height="4" fill="#a8742f"/>`,
    `<path d="M10 30 Q8 2 32 2 Q56 2 54 30 Q50 14 32 14 Q14 14 10 30Z" fill="#2a2450"/>`,
    `<path d="M12 22 L32 -2 L52 22Z" fill="#2a1d42"/><rect x="10" y="20" width="44" height="5" rx="2" fill="#7b3fb0"/>`,
  ];
  function avatar(name, opts = {}) {
    const h = hash(name || "?");
    const pick = (arr, k) => arr[(h >>> k) % arr.length];
    const skin = pick(SKIN, 1), hair = pick(HAIR, 4), cloth = pick(CLOTH, 8);
    const hat = (h >>> 12) % 5 === 0 ? pick(HATS.slice(1), 14) : "";
    const hairSvg = hat ? "" : pick(HAIRS, 17)(hair);
    const eyeY = 33 + ((h >>> 20) % 3);
    const smile = ["M26 44 Q32 48 38 44", "M27 45 L37 45", "M26 45 Q32 42 38 45", "M27 44 Q32 49 37 44"][(h >>> 22) % 4];
    const blush = (h >>> 24) % 2 ? `<circle cx="21" cy="41" r="3" fill="#ff8a7a" opacity=".35"/><circle cx="43" cy="41" r="3" fill="#ff8a7a" opacity=".35"/>` : "";
    const beard = (h >>> 26) % 6 === 0 ? `<path d="M18 40 Q20 56 32 56 Q44 56 46 40 Q40 48 32 48 Q24 48 18 40Z" fill="${hair}"/>` : "";
    const bg = `hsl(${h % 360} 45% 30%)`;
    return `<svg class="portrait" viewBox="0 0 64 64">
      <rect width="64" height="64" fill="${bg}"/><circle cx="32" cy="70" r="30" fill="${bg}" opacity=".6"/>
      <path d="M6 64 Q8 50 32 50 Q56 50 58 64Z" fill="${cloth}"/>
      <path d="M26 50 L32 58 L38 50Z" fill="${skin}"/>
      <ellipse cx="32" cy="35" rx="17" ry="19" fill="${skin}"/>
      ${beard}${hairSvg}${hat}
      <ellipse cx="25" cy="${eyeY}" rx="2.4" ry="2.8" fill="#1a120c"/><ellipse cx="39" cy="${eyeY}" rx="2.4" ry="2.8" fill="#1a120c"/>
      <circle cx="25.8" cy="${eyeY - 1}" r=".8" fill="#fff"/><circle cx="39.8" cy="${eyeY - 1}" r=".8" fill="#fff"/>
      ${blush}<path d="${smile}" stroke="#5a2a1a" stroke-width="2" fill="none" stroke-linecap="round"/>
    </svg>`;
  }

  // ---------- 场景：远山 + 村庄剪影 + 树林（颜色走 CSS 变量） ----------
  const village = () => `<svg class="village" viewBox="0 0 1600 360" preserveAspectRatio="xMidYMax slice">
    <path d="M0 210 L120 150 L240 196 L380 120 L520 190 L660 140 L800 200 L960 110 L1120 186 L1260 130 L1420 190 L1600 140 L1600 360 L0 360Z" fill="var(--hill1)"/>
    <path d="M0 260 Q200 220 400 250 T800 240 T1200 250 T1600 230 L1600 360 L0 360Z" fill="var(--hill2)"/>
    <g fill="var(--house)">
      <path d="M180 270 L180 228 L214 200 L248 228 L248 270Z"/><path d="M170 232 L214 194 L258 232Z" fill="var(--roof)"/>
      <path d="M300 270 L300 214 L346 178 L392 214 L392 270Z"/><path d="M288 218 L346 172 L404 218Z" fill="var(--roof)"/>
      <rect x="356" y="160" width="12" height="30"/>
      <path d="M1180 270 L1180 222 L1222 190 L1264 222 L1264 270Z"/><path d="M1168 226 L1222 184 L1276 226Z" fill="var(--roof)"/>
      <path d="M1310 270 L1310 234 L1338 212 L1366 234 L1366 270Z"/><path d="M1300 238 L1338 206 L1376 238Z" fill="var(--roof)"/>
      <path d="M1440 270 L1440 120 L1452 100 L1464 120 L1464 270Z"/><path d="M1430 124 L1452 70 L1474 124Z" fill="var(--roof)"/>
    </g>
    <g fill="var(--window)" class="windows">
      <rect x="206" y="236" width="12" height="12"/><rect x="330" y="226" width="14" height="14"/><rect x="356" y="226" width="14" height="14"/>
      <rect x="1212" y="232" width="14" height="14"/><rect x="1330" y="242" width="10" height="10"/><rect x="1448" y="140" width="8" height="12"/>
    </g>
    <g fill="var(--tree)">
      ${[60, 100, 460, 520, 1060, 1110, 1540].map((x, i) => `<path d="M${x} 280 L${x - 26 - i % 3 * 6} 280 L${x} ${180 - i % 3 * 24} L${x + 26 + i % 3 * 6} 280Z"/>`).join("")}
    </g>
    <path d="M0 300 Q400 270 800 290 T1600 280 L1600 360 L0 360Z" fill="var(--ground)"/>
  </svg>`;

  // ---------- 篝火（桌面中心） ----------
  const fire = () => `<svg class="fire" viewBox="0 0 120 120">
    <defs><radialGradient id="fi-g" cx="50%" cy="60%" r="50%"><stop offset="0" stop-color="#ffcf6a" stop-opacity=".9"/>
    <stop offset="1" stop-color="#ff6a00" stop-opacity="0"/></radialGradient></defs>
    <circle cx="60" cy="74" r="56" fill="url(#fi-g)" class="fire-glow"/>
    <g class="flames"><path class="fl1" d="M60 18 Q84 50 76 76 Q70 92 60 92 Q50 92 44 76 Q36 50 60 18Z" fill="#ff7a1a"/>
    <path class="fl2" d="M60 40 Q74 60 70 78 Q66 88 60 88 Q54 88 50 78 Q46 60 60 40Z" fill="#ffb02e"/>
    <path class="fl3" d="M60 58 Q66 70 64 80 Q62 86 60 86 Q58 86 56 80 Q54 70 60 58Z" fill="#fff1a8"/></g>
    <path d="M30 96 L90 84 M30 84 L90 96" stroke="#5a3618" stroke-width="9" stroke-linecap="round"/>
    <path d="M30 96 L90 84" stroke="#3a2410" stroke-width="3" stroke-linecap="round"/>
  </svg>`;

  const moon = () => `<svg viewBox="0 0 100 100"><defs><radialGradient id="mo-g" cx="40%" cy="38%" r="60%">
    <stop offset="0" stop-color="#fffbe9"/><stop offset=".7" stop-color="#f2d48f"/><stop offset="1" stop-color="#c9a35a"/></radialGradient></defs>
    <circle cx="50" cy="50" r="46" fill="url(#mo-g)"/><circle cx="36" cy="38" r="8" fill="#e2c27c" opacity=".55"/>
    <circle cx="62" cy="62" r="11" fill="#e2c27c" opacity=".45"/><circle cx="64" cy="32" r="5" fill="#e2c27c" opacity=".5"/></svg>`;
  const sun = () => `<svg viewBox="0 0 100 100"><defs><radialGradient id="su-g" cx="50%" cy="50%" r="50%">
    <stop offset="0" stop-color="#fff6cf"/><stop offset=".6" stop-color="#ffcf4d"/><stop offset="1" stop-color="#ff9f1c"/></radialGradient></defs>
    <g class="rays" stroke="#ffd46b" stroke-width="4" stroke-linecap="round" opacity=".8">
    ${Array.from({ length: 12 }, (_, i) => { const a = i * Math.PI / 6; return `<line x1="${50 + 40 * Math.cos(a)}" y1="${50 + 40 * Math.sin(a)}" x2="${50 + 48 * Math.cos(a)}" y2="${50 + 48 * Math.sin(a)}"/>`; }).join("")}</g>
    <circle cx="50" cy="50" r="32" fill="url(#su-g)"/></svg>`;
  return { card, avatar, village, fire, moon, sun, ROLE_ART };
})();
