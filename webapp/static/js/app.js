// 月下狼人杀 · 前端逻辑
// 后端推结构化消息（feed.kind = phase/speech/vote/notice/wolf/private/...，另有 dead / vote_result / game_over），
// 这里负责：圆桌舞台、过场动画、决策面板、纪事流、终局与历史回放。
"use strict";

const $ = id => document.getElementById(id);
const feed = $("feed");

const ROLES = {
  werewolf: { name: "狼人", camp: "狼人阵营", desc: "夜里与队友商量刀人；白天藏好身份，把票带到好人头上。" },
  seer:     { name: "预言家", camp: "好人 · 神职", desc: "每晚查验一人是好是狼。白天想办法让村民相信你。" },
  witch:    { name: "女巫", camp: "好人 · 神职", desc: "一瓶解药、一瓶毒药，各限一次，同一晚只能用一瓶。" },
  hunter:   { name: "猎人", camp: "好人 · 神职", desc: "死亡时（被毒除外）可以开枪带走一名存活玩家。" },
  villager: { name: "平民", camp: "好人 · 平民", desc: "没有技能。靠听发言、看投票，把狼找出来。" },
  random:   { name: "随机", camp: "命运安排", desc: "每局随机发牌，什么身份都有可能。" },
};
const ROLE_BY_NAME = Object.fromEntries(Object.entries(ROLES).map(([k, v]) => [v.name, k]));
const ASK_META = {  // 决策类型 → 面板标题 / 插画 / 配色
  speak:     { kicker: "轮到你发言" },
  vote:      { kicker: "放逐投票", art: "villager" },
  wolf_chat: { kicker: "狼人频道", art: "werewolf", cls: "kill" },
  kill:      { kicker: "今夜猎杀", art: "werewolf", cls: "kill" },
  check:     { kicker: "预言家查验", art: "seer", cls: "check" },
  save:      { kicker: "女巫 · 解药", art: "witch", cls: "save" },
  poison:    { kicker: "女巫 · 毒药", art: "witch", cls: "poison" },
  shoot:     { kicker: "猎人开枪", art: "hunter", cls: "kill" },
};

// ---------- 全局状态 ----------
let ws, selCfg = "6p", selRole = "random";
let gameEnded = false, liveDiscuss = false, replaying = false;
let players = [];          // [{name, alive, afk, role, check}]
let myName = "", myRole = "", mates = [];
let votes = {};            // 本轮投票：投票人 → 被投人（null = 弃权）
let voteBlock = null;      // 纪事里当前轮的投票卡
let thinking = "";         // 正在思考/发言的玩家
let picking = null;        // 当前可以直接点座位作答的候选集合
let round = 0, phase = "";
let roomMode = false, isHost = false, myToken = "", myNick = "", nicknames = {};

const esc = s => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const rich = s => esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
const mini = name => `<span class="mini">${ART.avatar(name)}</span>`;
const findP = name => players.find(p => p.name === name);
const send = m => ws && ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify(m));

function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("show"), 2800);
}

// ---------- 世界：星空 / 村庄 / 日月 ----------
(function buildWorld() {
  let html = "";
  for (let i = 0; i < 140; i++) {
    const s = Math.random() < .12 ? 3 : Math.random() < .4 ? 2 : 1;
    html += `<i style="left:${Math.random() * 100}%;top:${Math.random() * 70}%;width:${s}px;height:${s}px;` +
            `--d:${2 + Math.random() * 5}s;animation-delay:${-Math.random() * 6}s"></i>`;
  }
  $("stars").innerHTML = html;
  $("village").innerHTML = ART.village();
  document.querySelector("#celestial .moon").innerHTML = ART.moon();
  document.querySelector("#celestial .sun").innerHTML = ART.sun();
  $("fire").innerHTML = ART.fire();
  $("brand-icon").innerHTML = ART.moon();
})();

// ---------- 圆桌 ----------
function seatPos(i, n) {
  // 椭圆排座，1 号位在正上方顺时针；手机竖屏用正圆
  const round = window.innerWidth <= 900;
  const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
  return { x: 50 + (round ? 38 : 41) * Math.cos(a), y: 50 + (round ? 38 : 39) * Math.sin(a) };
}

function renderTable() {
  const n = players.length;
  const tally = {};
  Object.values(votes).forEach(t => { if (t) tally[t] = (tally[t] || 0) + 1; });
  $("seats").innerHTML = players.map((p, i) => {
    const { x, y } = seatPos(i, n);
    const me = p.name === myName;
    const cls = ["seat", me && "me", mates.includes(p.name) && "mate", !p.alive && "dead",
      p.afk && p.alive && "afk", thinking === p.name && p.alive && "speaking",
      picking && picking.has(p.name) && "pickable"].filter(Boolean).join(" ");
    let sub = me ? "你" : nicknames[p.name] ? esc(nicknames[p.name]) : "";
    if (p.afk && p.alive) sub = "AI 托管中";
    if (p.role) sub = `<span style="color:${roleColor(p.role)}">${esc(p.role)}</span>`;
    let tag = "";
    if (mates.includes(p.name)) tag = "🐺";
    else if (p.check === "狼人") tag = "🩸";
    else if (p.check) tag = "✅";
    const vt = tally[p.name] ? `<div class="votes">${"<i></i>".repeat(tally[p.name])}</div>` : "";
    const th = thinking === p.name && p.alive ? `<div class="think">···</div>` : "";
    return `<div class="${cls}" data-name="${esc(p.name)}" style="left:${x}%;top:${y}%">
      <div class="pf"><div class="pf-in">${ART.avatar(p.name)}</div><span class="no">${i + 1}</span>
      ${tag ? `<span class="tag">${tag}</span>` : ""}${vt}${th}</div>
      <div class="nm">${esc(p.name)}</div>${sub ? `<div class="sub">${sub}</div>` : ""}</div>`;
  }).join("") + voteLines();
  const alive = players.filter(p => p.alive).length;
  if (n && !gameEnded) $("hearth-sub").textContent = `存活 ${alive} / ${n}`;
}
function roleColor(roleName) {
  return { 狼人: "var(--wolf)", 预言家: "var(--seer)", 女巫: "var(--witch)", 猎人: "var(--hunter)" }[roleName] || "var(--villager)";
}
function voteLines() {  // 投票阶段：座位之间画红色虚线箭头
  const n = players.length;
  const idx = Object.fromEntries(players.map((p, i) => [p.name, i]));
  const lines = Object.entries(votes).filter(([, t]) => t && idx[t] !== undefined).map(([v, t]) => {
    const a = seatPos(idx[v], n), b = seatPos(idx[t], n);
    const k = 0.8;  // 终点停在目标头像外侧
    return `<line x1="${a.x}" y1="${a.y}" x2="${a.x + (b.x - a.x) * k}" y2="${a.y + (b.y - a.y) * k}"/>`;
  }).join("");
  return lines ? `<svg id="votelines" viewBox="0 0 100 100" preserveAspectRatio="none"><defs>
    <marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
    <path d="M0 0L10 5L0 10z" fill="#ff3d5e"/></marker></defs>${lines}</svg>` : "";
}
$("seats").addEventListener("click", e => {
  const s = e.target.closest(".seat.pickable");
  if (s) answer(s.dataset.name);
});
window.addEventListener("resize", () => players.length && renderTable());

// ---------- 昼夜 ----------
function setPhase(kind, r) {
  if (kind === phase && r === round) return;
  const changed = phase && kind !== phase;
  phase = kind; round = r;
  document.body.classList.toggle("night", kind !== "day");
  document.body.classList.toggle("day", kind === "day");
  if (changed && !replaying) {
    const c = $("celestial");
    c.classList.remove("rise"); void c.offsetWidth; c.classList.add("rise");
  }
  if (!kind) { $("phase-pill").classList.add("hidden"); return; }
  $("phase-pill").classList.remove("hidden");
  $("phase-icon").innerHTML = kind === "night" ? ART.moon() : ART.sun();
  $("phase-text").textContent = kind === "night" ? "夜" : "昼";
  $("phase-sub").textContent = `第 ${r} 轮`;
  $("hearth-title").textContent = kind === "night" ? "天黑请闭眼" : "天亮了";
  if (!replaying) banner(kind, `第 ${r} 轮`, kind === "night" ? "天 黑 了" : "天 亮 了",
    kind === "night" ? "狼人、预言家、女巫依次行动" : "村民们睁开眼睛");
}
let pendingBanner = null;
function banner(cls, kicker, title, sub) {
  if (!$("reveal").classList.contains("hidden")) { pendingBanner = [cls, kicker, title, sub]; return; }
  const b = $("banner");
  b.className = cls;
  b.querySelector(".b-kicker").textContent = kicker;
  b.querySelector(".b-title").textContent = title;
  b.querySelector(".b-sub").textContent = sub || "";
  void b.offsetWidth;
  b.classList.add("show");
}

// ---------- 纪事（信息流） ----------
function push(el) {
  const near = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 200;
  feed.appendChild(el);
  if (near || replaying) feed.scrollTop = feed.scrollHeight;
  return el;
}
function node(cls, html) {
  const d = document.createElement("div");
  d.className = "f " + cls;
  d.innerHTML = html;
  return d;
}
function speechNode(who, text, extra = "", tag = "") {
  const me = who === myName;
  const nick = nicknames[who] && !me ? `<small>${esc(nicknames[who])}</small>` : "";
  return node(`f-speech${me ? " me" : ""} ${extra}`, `${mini(who)}<div class="bubble">
    <div class="who">${esc(who)}${me ? "（你）" : ""}${nick}${tag}</div><div class="txt">${rich(text)}</div></div>`);
}

function onFeed(m) {
  switch (m.kind) {
    case "phase":
      votes = {}; voteBlock = null; thinking = "";
      setPhase(m.phase, m.round);
      renderTable();
      push(node(`f-phase ${m.phase}`, `<span class="pi">${m.phase === "night" ? ART.moon() : ART.sun()}</span>` +
        `第 ${m.round} 轮 · ${m.phase === "night" ? "夜" : "昼"}`));
      $("chron-sub").textContent = `第 ${m.round} 轮`;
      return;
    case "speech":
      if (thinking === m.speaker) { thinking = ""; renderTable(); }
      return push(speechNode(m.speaker, m.text));
    case "vote": return addVote(m.voter, m.target);
    case "notice": return onNotice(m.text);
    case "wolf":
      return push(speechNode(m.speaker || "狼人频道", m.text, "wolfchat", "<small>🐺 狼人频道</small>"));
    case "private": return addPrivate(m.text);
    case "end": return push(node("f-end", `🏁 游戏结束<br><span style="font-size:13px;font-weight:500">${esc(m.text)}</span>`));
    case "wolf_replay": return push(node("f-wolf-replay", rich(m.text)));
    case "reveal": return;  // 终局面板里有身份牌，纪事里不重复
    default: return push(node("f-sys", rich(m.text)));
  }
}

function onNotice(text) {
  const death = /死亡|放逐出局|带走/.test(text);
  push(node(`f-notice${death ? " death" : ""}`, rich(text)));
  if (replaying) return;
  let m;
  if ((m = text.match(/第\d+轮夜晚，(.+?) 死亡/))) banner("death", "昨 夜", `${m[1]} 倒下了`, "村庄里又少了一个人");
  else if (/平安夜/.test(text)) banner("day", "昨 夜", "平 安 夜", "无人死亡");
  else if ((m = text.match(/(\S+) 被放逐出局/))) {
    const shot = text.match(/开枪带走了 (\S+?)。/);
    banner("death", "放 逐", `${m[1]} 出局`, shot ? `猎人开枪带走了 ${shot[1]}` : "村民们做出了选择");
  } else if (/平票/.test(text)) banner("day", "投 票", "平 票", "本轮无人被放逐");
}

function addVote(voter, target) {
  votes[voter] = target;
  if (!voteBlock) voteBlock = push(node("f-votes", `<div class="vt">🗳️ 放逐投票</div><div class="bars"></div>`));
  renderVoteBlock();
  renderTable();
}
function renderVoteBlock() {
  const groups = {};
  Object.entries(votes).forEach(([v, t]) => (groups[t || ""] ||= []).push(v));
  const max = Math.max(0, ...Object.entries(groups).filter(([t]) => t).map(([, vs]) => vs.length));
  const rows = Object.entries(groups).sort((a, b) => (!a[0]) - (!b[0]) || b[1].length - a[1].length);
  voteBlock.querySelector(".bars").innerHTML = rows.map(([t, vs]) =>
    `<div class="vbar${!t ? " abst" : vs.length === max ? " top" : ""}"><div class="vn">${t ? esc(t) : "弃权"}${t ? ` · ${vs.length}` : ""}</div>` +
    `<div class="vv">${vs.map(v => `<span>${esc(v)}</span>`).join("")}</div></div>`).join("");
}

function addPrivate(text) {
  // 预言家查验结果：做成卡片，并在座位上打标记（🩸 狼 / ✅ 好人）
  const m = text.match(/查验了\s*(\S+?)，他是【(.+?)】/);
  if (m) {
    const p = findP(m[1]);
    if (p) { p.check = m[2]; renderTable(); }
    const bad = m[2] === "狼人";
    return push(node(`f-check ${bad ? "bad" : "good"}`, `${mini(m[1])}<div><div class="xs muted">🔮 ${esc(text.split("：")[0])} · 查验结果</div>` +
      `<div><b style="color:var(--text)">${esc(m[1])}</b> 是 <span class="res">${esc(m[2])}</span></div></div>`));
  }
  push(node("f-private", rich(text)));
}

function onDead(name) {
  const p = findP(name);
  if (!p || !p.alive) return;
  p.alive = false;
  renderTable();
  if (replaying) return;
  const el = document.querySelector(`.seat[data-name="${CSS.escape(name)}"]`);
  if (el) el.classList.add("dying");
}

// ---------- 决策面板 ----------
let maxChars = 0, timerT = null;
function hideAsk() {
  $("ask").classList.add("hidden");
  $("idle").classList.remove("hidden");
  $("choices").innerHTML = "";
  $("textrow").classList.add("hidden");
  clearInterval(timerT);
  if (picking) { picking = null; renderTable(); }
  maxChars = 0;
}
function setIdle(text) {
  $("idle-text").textContent = text;
  document.querySelector("#idle .spinner").classList.toggle("hidden", gameEnded);
}

function showAsk(m) {
  const meta = ASK_META[m.action] || { kicker: "轮到你了" };
  const ask = $("ask");
  ask.className = meta.cls || "";
  $("ask-kicker").textContent = meta.kicker;
  $("ask-prompt").textContent = m.prompt;
  const artRole = meta.art || myRole || "villager";
  $("ask-art").innerHTML = ART.card(artRole);
  const ch = $("choices");
  ch.innerHTML = "";
  if (m.kind === "choice") {
    $("textrow").classList.add("hidden");
    const names = m.candidates.filter(c => findP(c));
    m.candidates.forEach(c => {
      const b = document.createElement("button");
      const isName = !!findP(c);
      b.className = "choice" + (isName ? "" : " plain") + (c === "救" ? " yes" : "");
      b.innerHTML = isName ? `${mini(c)}${esc(c)}${c === myName ? "（你）" : mates.includes(c) ? "（队友）" : ""}` : esc(c);
      b.onclick = () => answer(c);
      ch.appendChild(b);
    });
    if (m.allow_abstain) {
      const b = document.createElement("button");
      b.className = "choice plain abstain";
      b.textContent = m.action === "poison" ? "不用毒药" : m.action === "shoot" ? "不开枪" : "弃权";
      b.onclick = () => answer("");
      ch.appendChild(b);
    }
    // 候选是玩家时，也可以直接点圆桌上的头像
    picking = names.length ? new Set(names) : null;
    renderTable();
  } else {
    const lim = m.prompt.match(/≤\s*(\d+)\s*字/);
    maxChars = lim ? +lim[1] : 0;
    $("textrow").classList.remove("hidden");
    $("textin").placeholder = m.action === "wolf_chat" ? "和队友商量今晚的战术…" : "说出你的推理…（Enter 发送）";
    updateCounter();
    setTimeout(() => $("textin").focus(), 50);
  }
  $("idle").classList.add("hidden");
  ask.classList.remove("hidden");
  startTimer(m.timeout);
  if (document.hidden && window.Notification?.permission === "granted")
    new Notification("🐺 轮到你了", { body: m.prompt });
}

function startTimer(sec) {
  clearInterval(timerT);
  const box = $("ask-timer");
  if (!sec) { box.classList.add("hidden"); return; }
  box.classList.remove("hidden");
  const end = Date.now() + sec * 1000, C = 106.8;
  const tick = () => {
    const left = Math.max(0, (end - Date.now()) / 1000);
    $("timer-num").textContent = Math.ceil(left);
    $("timer-arc").style.strokeDashoffset = C * (1 - left / sec);
    $("timer-arc").style.stroke = left < 15 ? "var(--blood)" : "var(--gold)";
    if (left <= 0) clearInterval(timerT);
  };
  tick();
  timerT = setInterval(tick, 500);
}

function answer(text) {
  send({ t: "answer", text });
  hideAsk();
  setIdle("等待其他人行动…");
}

function updateCounter() {
  const c = $("counter");
  if (!maxChars) { c.textContent = ""; return; }
  const n = [...$("textin").value].length;
  c.textContent = `${n}/${maxChars}`;
  c.classList.toggle("over", n > maxChars);
}
$("textin").addEventListener("input", updateCounter);
$("sendbtn").onclick = () => {
  const v = $("textin").value.trim();
  if (!v) { $("textin").focus(); return; }
  answer(v);
  $("textin").value = "";
};
$("textin").addEventListener("keydown", e => { if (e.key === "Enter" && !e.isComposing) $("sendbtn").onclick(); });

function onThinking(m) {
  const who = m.on && m.phase !== "post_game" ? (m.player || "") : "";
  if (who !== thinking) { thinking = who; renderTable(); }
  if ($("ask").classList.contains("hidden"))
    setIdle(m.on && m.label ? m.label.replace(/^\S+\s/, "") : phase === "night" ? "夜色深沉…" : "等待中…");
}

// ---------- 语音输入（浏览器自带识别，结果填进输入框，确认后手动发送） ----------
function setupMic(btn, input) {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { btn.style.display = "none"; return; }
  let rec = null, active = false;
  btn.onclick = () => {
    if (active) { rec.stop(); return; }
    rec = new SR();
    rec.lang = "zh-CN";
    rec.interimResults = true;
    const base = input.value.trim() ? input.value.trim() + " " : "";
    rec.onresult = e => {
      let txt = "";
      for (const r of e.results) txt += r[0].transcript;
      input.value = base + txt;
      input.dispatchEvent(new Event("input"));
    };
    const stop = () => { active = false; btn.classList.remove("recording"); };
    rec.onend = stop;
    rec.onerror = e => {
      stop();
      if (e.error === "not-allowed") toast("🎤 麦克风权限被拒绝，请在地址栏允许后重试");
      else if (e.error === "network") toast("🎤 语音识别需要联网，这次先用键盘吧");
    };
    active = true;
    btn.classList.add("recording");
    try { rec.start(); } catch { stop(); }
  };
}
setupMic($("micbtn"), $("textin"));
setupMic($("micbtn2"), $("discuss-in"));

// ---------- 身份牌 ----------
function showMyCard(role, roleName) {
  const el = $("mycard");
  el.className = role;
  el.innerHTML = ART.card(role) + `<div class="cap">${esc(roleName)}</div>`;
}
function revealRole(role, roleName, mateStr) {
  const info = ROLES[role] || ROLES.villager;
  const box = $("reveal");
  box.querySelector(".back").innerHTML = ART.card("back");
  box.querySelector(".front").innerHTML = ART.card(role);
  const nm = box.querySelector(".reveal-name");
  nm.textContent = roleName;
  nm.style.color = roleColor(roleName);
  box.querySelector(".reveal-desc").innerHTML = `<b>${info.camp}</b> · ${esc(info.desc)}`;
  box.querySelector(".reveal-mates").textContent = mateStr ? `🐺 你的狼队友：${mateStr}` : "";
  const flip = box.querySelector(".flip");
  flip.classList.remove("open");
  box.classList.remove("hidden");
  setTimeout(() => flip.classList.add("open"), 500);
  clearTimeout(revealRole._t);
  revealRole._t = setTimeout(closeReveal, 7000);  // 不点也会自动收起，避免挡住第一夜的操作
}
function closeReveal() {
  $("reveal").classList.add("hidden");
  if (pendingBanner) { const b = pendingBanner; pendingBanner = null; banner(...b); }
}
$("reveal-ok").onclick = closeReveal;
$("mycard").onclick = () => myRole && revealRole(myRole, ROLES[myRole].name, mates.join("、"));

// ---------- 大厅 ----------
const DECK = ["werewolf", "seer", "random", "witch", "hunter", "villager"];
function renderDeck() {
  const n = DECK.length;
  $("role-opts").innerHTML = DECK.map((r, i) => {
    const off = i - (n - 1) / 2;
    const dis = r === "hunter" && selCfg !== "8p";
    return `<button class="rcard${r === selRole ? " sel" : ""}${dis ? " disabled" : ""}" data-v="${r}"
      style="--rot:${off * 4}deg;--ty:${Math.abs(off) * 8}px">${ART.card(r === "random" ? "back" : r)}
      <div class="cap"><b>${ROLES[r].name}</b><small>${ROLES[r].camp}</small></div></button>`;
  }).join("");
  const info = ROLES[selRole];
  $("role-desc").innerHTML = `你将扮演 <b>${info.name}</b> —— ${esc(info.desc)}`;
}
$("role-opts").addEventListener("click", e => {
  const b = e.target.closest(".rcard");
  if (!b || b.classList.contains("disabled")) return;
  selRole = b.dataset.v;
  renderDeck();
});
function bindOpts(id, cb) {
  $(id).addEventListener("click", e => {
    const b = e.target.closest(".opt");
    if (!b || b.classList.contains("locked")) return;
    $(id).querySelectorAll(".opt").forEach(x => x.classList.toggle("sel", x === b));
    cb(b.dataset.v);
  });
}
bindOpts("cfg-opts", v => {
  selCfg = v;
  if (v !== "8p" && selRole === "hunter") selRole = "random";  // 猎人只在 8 人局
  renderDeck();
});
renderDeck();

function showOnly(id) {  // 大厅 / 房间 / 对局 三选一
  $("lobby").classList.toggle("hidden", id !== "lobby");
  $("roomlobby").classList.toggle("hidden", id !== "roomlobby");
  document.body.classList.toggle("phase-lobby", id !== "game");
  $("btn-home").classList.toggle("hidden", id !== "game");
  if (id !== "game") { setPhase(null); document.body.classList.add("night"); }
}

function resetGame() {
  feed.innerHTML = "";
  ["endpanel", "btn-end", "mycard", "reveal"].forEach(i => $(i).classList.add("hidden"));
  gameEnded = false;
  players = []; mates = []; myRole = ""; votes = {}; voteBlock = null; thinking = ""; phase = ""; round = 0;
  $("hearth-title").textContent = "等待开局";
  $("hearth-sub").textContent = "";
  $("chron-sub").textContent = "";
  hideAsk();
  setIdle("村民们正在入座…");
  renderTable();
}

// ---------- 连接 ----------
const wsUrl = () => `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
function connect(first) {
  ws = new WebSocket(wsUrl());
  ws.onmessage = ev => handle(JSON.parse(ev.data));
  ws.onopen = () => send(first || { t: "history" });
  ws.onclose = () => {
    $("status").textContent = "连接已断开";
    if (roomMode) { roomMode = false; toast("与房间的连接断开了"); showOnly("lobby"); connect(); }
    else if (!gameEnded && !document.body.classList.contains("phase-lobby")) toast("连接已断开，刷新页面重开");
  };
}
connect();
const refreshHistory = () => send({ t: "history" });

$("startbtn").onclick = () => {
  if (window.Notification?.permission === "default") Notification.requestPermission();
  resetGame();
  showOnly("game");
  $("status").textContent = "正在开局…";
  const msg = { t: "start", config: selCfg, role: selRole };
  if (ws.readyState === WebSocket.OPEN) send(msg);
  else connect(msg);
};
$("btn-home").onclick = () => {
  if (!gameEnded && !confirm("对局还在进行，回大厅会结束本局，确定吗？")) return;
  location.reload();
};
$("btn-chron").onclick = () => document.body.classList.toggle("chron-off");

// ---------- 服务端消息分发 ----------
function handle(m) {
  switch (m.t) {
    case "feed": onFeed(m); break;
    case "thinking": onThinking(m); break;
    case "ask": $("status").textContent = "轮到你了"; showAsk(m); break;
    case "role":
      myRole = m.role;
      mates = m.mates ? m.mates.split("、").filter(Boolean) : [];
      showMyCard(m.role, m.role_name);
      $("mycard").classList.remove("hidden");
      renderTable();
      if (!replaying) revealRole(m.role, m.role_name, m.mates);
      break;
    case "started":
      if (m.nicknames) nicknames = m.nicknames;
      if (roomMode) { resetGame(); showOnly("game"); }
      myName = m.name;
      $("status").textContent = `你坐在 ${m.name} 的位置`;
      players = m.players.map(name => ({ name, alive: true, afk: false }));
      renderTable();
      break;
    case "player_afk": { const p = findP(m.name); if (p) { p.afk = m.afk; renderTable(); } break; }
    case "dead": onDead(m.name); break;
    case "vote_result": break;  // 计票已由逐条投票实时呈现，这里只用于存档
    case "game_over": onGameOver(m); break;
    case "review":
      $("review-box").innerHTML = mdToHtml(m.md);
      refreshHistory();
      break;
    case "discuss_msg": addDiscuss(m.player, m.role_name, m.text); break;
    case "history_list": renderHistory(m.games); break;
    case "history_game": loadHistory(m.game); break;
    case "toast": toast(m.text); break;
    case "joined": roomMode = true; myToken = m.token; isHost = m.host; showOnly("roomlobby"); break;
    case "room_state": renderRoom(m); break;
    case "room_error": toast("⚠️ " + m.text); break;
  }
}

// ---------- 终局 ----------
function finalFrom(m) {  // 兼容旧存档：只有 reveal 文本时也能还原身份
  if (m.players?.length && m.players[0].role) return m.players;
  return (m.reveal || "").split("；").filter(Boolean).map(s => {
    const [name, r = ""] = s.split("=");
    const role_name = r.replace(/(存活|出局)$/, "");
    return { name, role_name, role: ROLE_BY_NAME[role_name], alive: findP(name)?.alive ?? true };
  });
}
function showEnd(winner, final, kicker, discuss) {
  const village = winner === "village";
  $("end-banner").className = village ? "village" : "werewolf";
  $("end-kicker").textContent = kicker;
  $("end-title").textContent = village ? "好人胜利" : "狼人胜利";
  const mine = final.find(p => p.name === myName);
  const won = mine && ((mine.role === "werewolf") === !village);
  $("end-sub").textContent = mine ? (won ? "🎉 你所在的阵营赢了" : "这局输了，看看复盘找找原因") : "";
  $("end-cards").innerHTML = final.map((p, i) => `<div class="ecard${p.alive === false ? " dead" : ""}${p.name === myName ? " me" : ""}"
    style="animation-delay:${i * 70}ms">${ART.card(p.role)}${p.alive === false ? '<span class="out">出局</span>' : ""}
    <div class="cap">${esc(p.name)}${p.name === myName ? "（你）" : ""}<small style="color:${roleColor(p.role_name)}">${esc(p.role_name)}</small></div></div>`).join("");
  $("tab-discuss").classList.toggle("hidden", !discuss);
  switchTab("review-box");
  $("discuss-log").innerHTML = "";
  $("discuss-quick").innerHTML = final.filter(p => p.name !== myName).map(p =>
    `<button data-n="${esc(p.name)}">${mini(p.name)}@${esc(p.name)}</button>`).join("");
  $("endpanel").classList.remove("hidden");
  $("btn-end").classList.remove("hidden");
}

function onGameOver(m) {
  gameEnded = true;
  liveDiscuss = true;
  hideAsk();
  thinking = ""; votes = {};
  const final = finalFrom(m);
  final.forEach(f => { const p = findP(f.name); if (p) { p.role = f.role_name; if (f.alive === false) p.alive = false; } });
  renderTable();
  setPhase(null);
  $("hearth-title").textContent = m.winner === "village" ? "好人胜利" : "狼人胜利";
  $("hearth-sub").textContent = "身份已揭晓";
  $("status").textContent = "对局结束";
  setIdle("对局结束");
  $("review-box").innerHTML = '<div class="loading"><span class="spinner"></span>解说员正在复盘…（可以先收起面板回看本局）</div>';
  banner(m.winner === "village" ? "day" : "death", "终 局", m.winner === "village" ? "好人胜利" : "狼人胜利", "");
  setTimeout(() => showEnd(m.winner, final, `第 ${m.rounds || round} 轮 · 终局`, true), 1800);
}

// ---------- 往期对局 ----------
function renderHistory(games) {
  const el = $("hist-list");
  if (!games.length) { el.innerHTML = '<div class="muted xs">还没有对局记录，开一局吧</div>'; $("hist-stats").innerHTML = ""; return; }
  const mine = games.filter(g => g.human_role);
  const wins = mine.filter(g => (g.human_role === "werewolf") === (g.winner === "werewolf")).length;
  $("hist-stats").innerHTML = `<div class="hs"><b>${games.length}</b><small>对局</small></div>` +
    `<div class="hs"><b>${mine.length ? Math.round(wins / mine.length * 100) : 0}%</b><small>你的胜率</small></div>` +
    `<div class="hs"><b>${mine.filter(g => g.human_role === "werewolf").length}</b><small>当狼次数</small></div>`;
  el.innerHTML = "";
  games.forEach(g => {
    const won = g.human_role ? (g.human_role === "werewolf") === (g.winner === "werewolf") : null;
    const b = document.createElement("button");
    b.className = "hist-item";
    b.innerHTML = `<span class="hc">${ART.card(g.human_role || "back")}</span><div class="hm">
      <div><b>${g.winner === "village" ? "好人胜" : "狼人胜"}</b> · ${g.cfg === "8p" ? "8 人局" : "6 人局"}${g.rounds ? ` · ${g.rounds} 轮` : ""}${g.mode === "room" ? " · 多人" : ""}</div>
      <div class="ht">${esc(g.ts)}${g.human_role_name ? ` · 你是${esc(g.human_role_name)}` : ""}</div></div>
      ${won === null ? "" : `<span class="hw ${won ? "win" : "lose"}">${won ? "胜" : "负"}</span>`}`;
    b.onclick = () => send({ t: "load_history", id: g.id });
    el.appendChild(b);
  });
}

function loadHistory(g) {  // 按原顺序重放存档消息，不播放动画
  resetGame();
  showOnly("game");
  gameEnded = true;
  liveDiscuss = false;
  nicknames = g.humans || {};
  myName = g.human || "";
  players = (g.players || []).map(p => ({ name: p.name, alive: true, afk: false }));
  replaying = true;
  for (const e of g.feed) {
    if (e.t === "feed") onFeed(e);
    else if (e.t === "role") {
      myRole = e.role;
      mates = e.mates ? e.mates.split("、").filter(Boolean) : [];
      showMyCard(e.role, e.role_name);
      $("mycard").classList.remove("hidden");
    } else if (e.t === "dead") onDead(e.name);
  }
  replaying = false;
  const final = finalFrom({ players: g.final, reveal: g.reveal });
  final.forEach(f => { const p = findP(f.name); if (p) p.role = f.role_name; });
  votes = {};
  setPhase(null);
  renderTable();
  $("hearth-title").textContent = "往期回放";
  $("hearth-sub").textContent = g.ts;
  $("status").textContent = `回看 · ${g.ts}`;
  setIdle("这是一局往期对局的回放");
  $("review-box").innerHTML = mdToHtml(g.review || "（本局无复盘）");
  showEnd(g.winner, final, `往期回放 · ${g.ts}`, false);
  feed.scrollTop = feed.scrollHeight;
}

function mdToHtml(md) {
  let inCode = false;
  return md.split("\n").map(line => {
    if (line.startsWith("```")) { inCode = !inCode; return inCode ? "<pre>" : "</pre>"; }
    if (inCode) return esc(line) + "\n";
    const l = esc(line).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`(.+?)`/g, "<code>$1</code>");
    if (l.startsWith("### ")) return `<h4>${l.slice(4)}</h4>`;
    if (l.startsWith("## ")) return `<h3>${l.slice(3)}</h3>`;
    if (l.startsWith("# ")) return `<h3>${l.slice(2)}</h3>`;
    if (/^[-*] /.test(l)) return `<li>${l.slice(2)}</li>`;
    if (/^\d+\. /.test(l)) return `<li>${l}</li>`;
    return l.trim() ? `<p>${l}</p>` : "";
  }).join("");
}

// ---------- 终局面板 / 赛后讨论 ----------
function switchTab(pane) {
  document.querySelectorAll("#end-tabs .tab").forEach(t => t.classList.toggle("sel", t.dataset.pane === pane));
  $("review-box").classList.toggle("hidden", pane !== "review-box");
  $("discuss-box").classList.toggle("hidden", pane !== "discuss-box");
  if (pane === "discuss-box") $("discuss-in").focus();
}
$("end-tabs").addEventListener("click", e => { const t = e.target.closest(".tab"); if (t) switchTab(t.dataset.pane); });

function addDiscuss(player, roleName, text) {
  const name = player.replace(/（.*）$/, "");  // 房间模式里人类发言形如 "Alice（阿泽）"
  const tag = roleName ? `<small style="color:${roleColor(roleName)}">${esc(roleName)}</small>` : "";
  const el = speechNode(player === "你" ? myName : name, text, "", tag);
  $("discuss-log").appendChild(el);
  $("discuss-log").scrollTop = $("discuss-log").scrollHeight;
}
function sendDiscuss() {
  const inp = $("discuss-in");
  const q = inp.value.trim();
  if (!q || !liveDiscuss) return;
  if (!roomMode) addDiscuss("你", "", q);  // 房间模式服务端会广播回来
  send({ t: "discuss", text: q });
  inp.value = "";
  syncAskBtn();
}
function syncAskBtn() {
  const q = $("discuss-in").value.toLowerCase();
  const hit = players.some(p => p.name !== myName && new RegExp(`(?<![a-z])${p.name.toLowerCase()}(?![a-z])`).test(q));
  $("discuss-send").textContent = hit ? "点名提问" : "问全场";
}
$("discuss-in").addEventListener("input", syncAskBtn);
$("discuss-send").onclick = sendDiscuss;
$("discuss-in").addEventListener("keydown", e => { if (e.key === "Enter" && !e.isComposing) sendDiscuss(); });
$("discuss-quick").addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  const inp = $("discuss-in");
  inp.value = `${b.dataset.n} ` + inp.value.replace(/^\S+\s/, s => findP(s.trim()) ? "" : s);
  inp.focus();
  syncAskBtn();
});
const closeEnd = () => $("endpanel").classList.add("hidden");
$("btn-back").onclick = closeEnd;
$("btn-back2").onclick = closeEnd;
$("btn-end").onclick = () => gameEnded && $("endpanel").classList.remove("hidden");
$("btn-again").onclick = () => {
  closeEnd();
  if (roomMode) showOnly("roomlobby");
  else { showOnly("lobby"); refreshHistory(); }
};

// ==================== 多人房间 ====================
function enterRoom(first) {  // 房间模式需要新连接：服务端按首条消息路由
  if (ws) { ws.onclose = null; ws.close(); }
  connect(first);
}
$("tab-single").onclick = () => {
  $("tab-single").classList.add("sel"); $("tab-multi").classList.remove("sel");
  $("single-pane").classList.remove("hidden"); $("multi-pane").classList.add("hidden");
};
$("tab-multi").onclick = () => {
  $("tab-multi").classList.add("sel"); $("tab-single").classList.remove("sel");
  $("single-pane").classList.add("hidden"); $("multi-pane").classList.remove("hidden");
  $("nickin").focus();
};
const getNick = () => $("nickin").value.trim() || "玩家" + Math.floor(Math.random() * 90 + 10);
$("createroombtn").onclick = () => {
  myNick = getNick();
  localStorage.setItem("ww_nick", myNick);
  enterRoom({ t: "create_room", nickname: myNick });
};
$("joinroombtn").onclick = () => {
  const code = $("roomcodein").value.trim().toUpperCase();
  if (!code) { toast("请输入 4 位房间码"); $("roomcodein").focus(); return; }
  myNick = getNick();
  localStorage.setItem("ww_nick", myNick);
  enterRoom({ t: "join_room", room: code, nickname: myNick });
};
$("roomcodein").addEventListener("keydown", e => { if (e.key === "Enter") $("joinroombtn").onclick(); });
$("nickin").value = localStorage.getItem("ww_nick") || "";

function renderRoom(m) {
  $("roomcode").textContent = m.room;
  $("roomcount").textContent = `${m.players.length} 人${m.ai_fill ? ` + AI ${m.ai_fill}` : ""}`;
  const ai = Array.from({ length: m.ai_fill || 0 }, () => `<div class="rp ai"><span class="mini">🤖</span>AI 补位</div>`);
  $("roomplayers").innerHTML = m.players.map(p =>
    `<div class="rp${p.host ? " host" : ""}">${mini(p.nick)}${esc(p.nick)}${p.nick === myNick ? "（你）" : ""}` +
    `${p.host ? "<small>👑 房主</small>" : ""}</div>`).concat(ai).join("");
  isHost = m.players.find(p => p.nick === myNick)?.host ?? isHost;
  document.querySelectorAll("#room-cfg-opts .opt").forEach(b => {
    b.classList.toggle("sel", b.dataset.v === m.config);
    b.classList.toggle("locked", !isHost);
  });
  $("roomstartbtn").classList.toggle("hidden", !isHost);
  $("room-wait").classList.toggle("hidden", isHost);
  $("roomstartbtn").textContent = m.state === "ENDED" ? "再 来 一 局" : "入 夜";
}
$("room-cfg-opts").addEventListener("click", e => {
  const b = e.target.closest(".opt");
  if (b && isHost) send({ t: "set_config", config: b.dataset.v });
});
$("roomstartbtn").onclick = () => isHost && send({ t: "room_start" });
$("leaveroombtn").onclick = () => location.reload();
$("copycode").onclick = () => navigator.clipboard?.writeText($("roomcode").textContent).then(() => toast("房间码已复制"));
