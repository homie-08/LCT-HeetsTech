// Мок-данные по ТЗ 06-ui-spec.md — детерминированная генерация
let _s = 20260812;
const rnd = () => { _s = Math.imul(_s ^ (_s >>> 15), _s | 1); _s ^= _s + Math.imul(_s ^ (_s >>> 7), _s | 61); return ((_s ^ (_s >>> 14)) >>> 0) / 4294967296; };
const ri = (a, b) => a + Math.floor(rnd() * (b - a + 1));
const pick = (a) => a[Math.floor(rnd() * a.length)];
export const fmt = (m) => `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`;

export const EQUIPMENT = [
  { name: 'Кабельный тестер', qty: 8 },
  { name: 'Набор инструмента СКС', qty: 10 },
  { name: 'Рефлектометр оптический', qty: 2, deficit: true },
  { name: 'Сварочный аппарат для волокна', qty: 2, deficit: true },
  { name: 'Мегаомметр', qty: 2, deficit: true },
  { name: 'Тепловизор', qty: 2, deficit: true },
  { name: 'Программатор СКУД', qty: 2, deficit: true },
  { name: 'Стремянка 2,4 м', qty: 6, bulky: true },
  { name: 'Баллон с хладагентом R410A', qty: 4, bulky: true },
  { name: 'Тележка монтажная', qty: 3, bulky: true },
  { name: 'Перфоратор с буром', qty: 7 },
  { name: 'Паяльная станция', qty: 5 },
  { name: 'Мультиметр', qty: 12 },
  { name: 'Обжимной инструмент RJ-45', qty: 9 },
  { name: 'Трассоискатель кабельный', qty: 3 },
  { name: 'Анализатор спектра Wi-Fi', qty: 4 },
  { name: 'Шуруповёрт аккумуляторный', qty: 11 },
];
export const WORK_TYPES = [
  { name: 'Сети и СКС', label: 'Монтаж и расшивка СКС, кросс-панели', lvl: 2, eq: [0, 1, 13], dur: [50, 90] },
  { name: 'ВОЛС', label: 'Диагностика ВОЛС, сварка волокна', lvl: 3, eq: [2, 3], dur: [60, 95] },
  { name: 'СКУД', label: 'Настройка контроллеров СКУД', lvl: 2, eq: [6, 12], dur: [45, 80] },
  { name: 'Видеонаблюдение', label: 'Монтаж и юстировка камер наблюдения', lvl: 2, eq: [7, 10, 16], dur: [55, 90] },
  { name: 'Электрика', label: 'Замеры изоляции, ревизия электрощита', lvl: 3, eq: [4, 12], dur: [45, 85] },
  { name: 'Кондиционирование', label: 'Заправка и диагностика кондиционера', lvl: 2, eq: [8, 5], dur: [50, 80] },
  { name: 'Телефония', label: 'Перенос и настройка IP-телефонии', lvl: 1, eq: [0, 13], dur: [40, 70] },
  { name: 'Wi-Fi', label: 'Радиообследование и настройка Wi-Fi', lvl: 2, eq: [15, 7], dur: [45, 75] },
  { name: 'Пожарная сигнализация', label: 'Обслуживание пожарной сигнализации', lvl: 2, eq: [7, 12], dur: [50, 85] },
  { name: 'Серверное оборудование', label: 'Монтаж серверной стойки и коммутация', lvl: 3, eq: [9, 16], dur: [60, 95] },
  { name: 'Домофония', label: 'Ремонт домофона и вызывной панели', lvl: 1, eq: [11, 12], dur: [40, 70] },
  { name: 'ККТ и кассы', label: 'Замена фискального накопителя ККТ', lvl: 2, eq: [16], dur: [40, 65] },
];
export const WAREHOUSES = [
  { name: 'Склад Центр', addr: 'Костомаровский пер., 3, стр. 1', pt: { x: 500, y: 280 } },
  { name: 'Склад Восток', addr: 'ш. Энтузиастов, 56, стр. 32', pt: { x: 780, y: 220 } },
  { name: 'Склад Юго-Запад', addr: 'Научный пр-д, 8, стр. 1', pt: { x: 250, y: 430 } },
];
const CUSTOMERS = ['ООО «Вектор Плюс»', 'АО «СтройИнвест»', 'БЦ «Аврора Плаза»', 'ООО «Логистика-М»', 'Кафе «Тёплый хлеб»', 'ТЦ «Гагаринский»', 'ООО «МедиаСофт»', 'Клиника «Здоровье+»', 'Школа № 1298', 'ООО «Прогресс-Авто»', 'Гостиница «Пресня»', 'АО «ТехноРитейл»', 'Салон «Оптика Сити»', 'ООО «Фудмаркет Юг»', 'Типография «Литера»', 'Фитнес-клуб «Тонус»', 'ООО «Дента-Люкс»', 'Аптека «Вита-Норд»', 'ООО «Кванта Сервис»', 'Банк «Меридиан», ДО № 4'];
const STREETS = ['ул. Льва Толстого', 'Варшавское ш.', 'ул. Бауманская', 'Ленинградский пр-т', 'ул. Марксистская', 'Каширское ш.', 'ул. Профсоюзная', 'пр-т Мира', 'ул. Складочная', 'Волгоградский пр-т', 'ул. Автозаводская', 'ул. Стромынка', 'Дмитровское ш.', 'ул. Ордынка Б.', 'наб. Академика Туполева'];
const DISTRICTS = ['Хамовники', 'Таганский', 'Басманный', 'Пресненский', 'Даниловский', 'Сокольники', 'Марьина Роща', 'Лефортово', 'Останкинский', 'Замоскворечье'];
const addr = () => `${pick(STREETS)}, ${ri(2, 68)}${rnd() < 0.4 ? `, стр. ${ri(1, 4)}` : rnd() < 0.3 ? `, к. ${ri(1, 3)}` : ''}`;

const ENG_DEF = [
  ['Алексей Смирнов', 'car', 480, 1020, [[0, 3], [1, 2]], 0],
  ['Дмитрий Козлов', 'van', 480, 1080, [[3, 3], [2, 2]], 1],
  ['Иван Петров', 'foot', 540, 1080, [[6, 3], [0, 2]], null],
  ['Сергей Волков', 'car', 540, 1080, [[4, 4]], 2],
  ['Николай Орлов', 'van', 480, 1020, [[5, 3]], 1],
  ['Андрей Соколов', 'foot', 600, 1140, [[7, 3], [6, 2]], null],
  ['Михаил Зайцев', 'car', 480, 1020, [[8, 3], [4, 2]], 0],
  ['Павел Морозов', 'van', 540, 1140, [[9, 4], [0, 3]], 2],
  ['Егор Лебедев', 'foot', 480, 1020, [[10, 2], [2, 2]], null],
  ['Олег Виноградов', 'car', 540, 1080, [[1, 4], [0, 3]], 0],
  ['Роман Киселёв', 'car', 480, 1020, [[11, 3], [10, 2]], null],
  ['Виктор Титов', 'van', 600, 1140, [[3, 4], [4, 3]], 1],
  ['Артём Громов', 'foot', 540, 1080, [[0, 2], [6, 2]], null],
  ['Максим Фролов', 'car', 720, 1200, [[5, 2]], 1],
  ['Денис Крылов', 'foot', 480, 1020, [[11, 2]], null],
  ['Глеб Савельев', 'van', 840, 1320, [[4, 2], [8, 2]], 2],
  ['Юрий Белов', 'foot', 540, 1080, [[10, 1]], null],
  ['Кирилл Носов', 'car', 780, 1260, [[7, 2]], null],
];
const TRANSPORT = { car: 'Легковой', van: 'Фургон', foot: 'Пешком + метро' };
const VISIT_COUNTS = [4, 5, 4, 3, 6, 4, 2, 4, 5, 4, 3, 4, 3]; // = 51
const IDLE_REASONS = {
  13: 'Смена с 12:00 — дневные заявки его профиля уже разобраны утренней сменой',
  14: 'Заявки по ККТ закрыты Романом Киселёвым, уровень которого выше',
  15: 'Вечерняя смена с 14:00 — под неё пока не поступило подходящих заявок',
  16: 'Единственный навык — Домофония ур. 1, все заявки требуют минимум ур. 2',
  17: 'Смена с 13:00 — обе заявки Wi-Fi уместились в маршруты утренней смены',
};
// приоритеты: P1×5, P2×15, P3×33, P4×17
const PRIOS = [];
[['P1', 5], ['P2', 15], ['P3', 33], ['P4', 17]].forEach(([p, n]) => { for (let i = 0; i < n; i++) PRIOS.push(p); });
for (let i = PRIOS.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [PRIOS[i], PRIOS[j]] = [PRIOS[j], PRIOS[i]]; }

export const ENGINEERS = ENG_DEF.map(([name, tr, s0, s1, skills, wh], i) => {
  const busy = i < 13;
  const equip = [];
  skills.forEach(([t]) => WORK_TYPES[t].eq.forEach((e) => { if (!equip.includes(e)) equip.push(e); }));
  while (equip.length < (busy ? ri(5, 9) : ri(3, 5))) { const e = ri(0, 16); if (!equip.includes(e) && !(EQUIPMENT[e].bulky && tr === 'foot')) equip.push(e); }
  const cantTake = tr === 'foot' ? EQUIPMENT.filter((e) => e.bulky).map((e) => e.name) : [];
  return {
    id: 'e' + (i + 1), name, transport: tr, transportLabel: TRANSPORT[tr],
    shift: `${fmt(s0)}–${fmt(s1)}`, s0, s1, busy,
    color: busy ? `hsl(${(i * 137 + 40) % 360} 62% 55%)` : '#6b6b74',
    skills: skills.map(([t, l]) => ({ t, name: `${WORK_TYPES[t].name} ур. ${l}`, lvl: l })),
    wh: wh == null ? null : WAREHOUSES[wh].name, whIdx: wh,
    equip: equip.slice(0, 9).map((e) => EQUIPMENT[e].name),
    cantTake, idleReason: IDLE_REASONS[i] || null,
    home: { x: ri(80, 920), y: ri(70, 500) },
    visits: [], segs: [], pts: [], work: 0, road: 0, idleMin: 0, lunch: 0,
  };
});

export const JOBS = [];
let jn = 0;
const mkJob = (extra) => { jn++; const j = { id: 'j' + String(jn).padStart(2, '0'), ...extra }; JOBS.push(j); return j; };
const round5 = (m) => Math.round(m / 5) * 5;

// маршруты 13 занятых инженеров → 51 назначенная заявка
ENGINEERS.slice(0, 13).forEach((eng, ei) => {
  let t = eng.s0, x = eng.home.x, y = eng.home.y, hadLunch = false;
  eng.pts.push({ x, y, kind: 'home' });
  eng.segs.push({ k: 'start', t0: t, t1: t, label: 'Выезд' });
  if (eng.whIdx != null) {
    const wp = WAREHOUSES[eng.whIdx].pt;
    const tr = ri(12, 25); eng.segs.push({ k: 'travel', t0: t, t1: t + tr }); t += tr; eng.road += tr;
    eng.segs.push({ k: 'depot', t0: t, t1: t + 15, label: 'Склад' }); t += 15;
    eng.pts.push({ x: wp.x, y: wp.y, kind: 'wh' }); x = wp.x; y = wp.y;
  }
  for (let v = 0; v < VISIT_COUNTS[ei]; v++) {
    const trMin = eng.transport === 'foot' ? ri(18, 48) : ri(10, 34);
    const metro = eng.transport === 'foot' && rnd() < 0.6;
    const km = eng.transport === 'foot' ? +(trMin * 0.06).toFixed(1) : +(trMin * 0.55).toFixed(1);
    eng.segs.push({ k: 'travel', t0: t, t1: t + trMin, metro }); t += trMin; eng.road += trMin;
    let wait = 0;
    if (rnd() < 0.22) { wait = ri(5, 25); eng.segs.push({ k: 'idle', t0: t, t1: t + wait, label: 'Ожидание' }); t += wait; eng.idleMin += wait; }
    const skill = pick(eng.skills); const wt = WORK_TYPES[skill.t];
    const dur = round5(ri(wt.dur[0], wt.dur[1]) - (skill.lvl - wt.lvl) * 8);
    const wf = round5(Math.max(420, t - ri(0, 60))), wto = round5(t + dur + ri(30, 150));
    const hard = rnd() < 0.3;
    x = Math.max(60, Math.min(940, x + ri(-160, 160))); y = Math.max(50, Math.min(510, y + ri(-110, 110)));
    const job = mkJob({
      status: 'planned', prio: PRIOS[jn], customer: pick(CUSTOMERS), t: skill.t,
      typeName: wt.name, typeLabel: wt.label, district: pick(DISTRICTS), address: addr(),
      window: `${fmt(wf)}–${fmt(wto)}`, wf, wto, hard, sla: wto + ri(60, 180),
      eng: eng.id, engName: eng.name, order: v + 1, start: t, end: t + dur,
      fromPrev: `${trMin} мин · ${km} км`, wait, metro,
      equip: wt.eq.map((e) => EQUIPMENT[e].name), lvlNeed: wt.lvl, pinned: false,
      pt: { x, y },
    });
    job.slaViolated = job.end > job.sla - 0 ? false : false;
    eng.segs.push({ k: 'visit', t0: t, t1: t + dur, job: job.id, label: job.customer, hard, wait });
    eng.pts.push({ x, y, kind: 'visit', n: v + 1, job: job.id });
    t += dur; eng.work += dur;
    if (!hadLunch && t > 740) { eng.segs.push({ k: 'lunch', t0: t, t1: t + 45, label: 'Обед' }); t += 45; eng.lunch = 45; hadLunch = true; }
    eng.visits.push(job.id);
  }
  const trh = eng.transport === 'foot' ? ri(20, 45) : ri(12, 30);
  eng.segs.push({ k: 'travel', t0: t, t1: t + trh }); t += trh; eng.road += trh;
  eng.segs.push({ k: 'end', t0: t, t1: t, label: 'Возврат' });
  eng.pts.push({ x: eng.home.x, y: eng.home.y, kind: 'home' });
  eng.dayEnd = t;
});
// 3 нарушения SLA — назначим явно
['j07', 'j19', 'j33'].forEach((id) => { const j = JOBS.find((x) => x.id === id); j.slaViolated = true; j.sla = j.end - ri(10, 35); });
JOBS.forEach((j) => { if (!j.slaViolated) j.sla = Math.max(j.sla || 0, j.end + 30); });
// закреплённая диспетчером
const pinnedJob = JOBS.find((j) => j.id === 'j12'); pinnedJob.pinned = true;

// 1 неназначенная
export const UNASSIGNED = mkJob({
  status: 'unassigned', prio: 'P2', customer: 'БЦ «Аврора Плаза»', t: 2,
  typeName: 'СКУД', typeLabel: 'Настройка контроллеров СКУД', district: 'Пресненский',
  address: 'Пресненская наб., 12, подъезд 3', window: '09:00–13:10', wf: 540, wto: 790, hard: true,
  sla: 800, equip: ['Программатор СКУД', 'Мультиметр'], lvlNeed: 2, pinned: false,
  pt: { x: 330, y: 200 },
  verdict: 'Окно до 13:10 недостижимо: программатор СКУД занят',
  whyNot: [
    { eng: 'Дмитрий Козлов', engId: 'e2', text: 'Нет программатора СКУД — оба экземпляра выданы другим' },
    { eng: 'Егор Лебедев', engId: 'e9', text: 'Освобождается в 14:20 — жёсткое окно закрывается в 13:10' },
    { eng: 'Юрий Белов', engId: 'e17', text: 'Уровень 1 по СКУД, заявке требуется минимум уровень 2' },
  ],
});
// 18 новых (ещё не поступили)
for (let i = 0; i < 18; i++) {
  const t = ri(0, 11); const wt = WORK_TYPES[t];
  const at = 490 + i * 23;
  const wf = round5(at + ri(30, 120)), wto = wf + ri(90, 240);
  mkJob({
    status: 'new', prio: PRIOS[jn] || 'P3', customer: pick(CUSTOMERS), t,
    typeName: wt.name, typeLabel: wt.label, district: pick(DISTRICTS), address: addr(),
    window: `${fmt(wf)}–${fmt(wto)}`, wf, wto, hard: rnd() < 0.25, sla: wto + ri(60, 200),
    equip: wt.eq.map((e) => EQUIPMENT[e].name), lvlNeed: wt.lvl, arriveT: at, pinned: false,
    pt: { x: ri(80, 920), y: ri(60, 500) },
  });
}
// объяснения для назначенных
JOBS.filter((j) => j.status === 'planned').forEach((j) => {
  const eng = ENGINEERS.find((e) => e.id === j.eng);
  const cands = ENGINEERS.filter((e) => e.busy && e.id !== j.eng && e.skills.some((s) => s.t === j.t && s.lvl >= j.lvlNeed)).slice(0, ri(1, 5));
  const m1 = ri(8, 20), m2 = m1 + ri(8, 25);
  const lvl = eng.skills.find((s) => s.t === j.t)?.lvl || j.lvlNeed;
  j.explain = {
    why: [
      `Ближайший исполнитель: ${m1} мин от предыдущей точки против ${m2} мин у альтернативы`,
      `Уровень ${lvl} по типу «${j.typeName}» — норматив ${j.end - j.start} мин вместо ${j.end - j.start + (lvl - 1) * 8}`,
      `Весь нужный инструмент уже на руках: ${j.equip.slice(0, 2).join(', ').toLowerCase()}`,
    ],
    time: [
      `Окно клиента ${j.window} вмещает визит ${fmt(j.start)}–${fmt(j.end)} целиком${j.wait ? `, ожидание ${j.wait} мин` : ', без ожидания'}`,
      `Более ранний слот занят визитом с жёстким окном, более поздний добавил бы ${ri(4, 14)} км пробега`,
    ],
    alts: cands.map((c) => {
      const later = ri(25, 110), km = ri(3, 12);
      return { eng: c.name, engId: c.id, text: `Приезд не раньше ${fmt(j.start + later)}, на ${later} мин позже; +${km} км пробега службы`, cost: `+${ri(15, 60)} мин в пути` };
    }),
  };
});

export const EVENTS = [
  { t: 490, kind: 'Новая заявка', text: 'P3 · ТЦ «Гагаринский» — перенос точки IP-телефонии' },
  { t: 504, kind: 'Визит затянулся', text: 'Смирнов на объекте «Вектор Плюс»: +20 мин к работе' },
  { t: 520, kind: 'Новая заявка', text: 'P4 · Аптека «Вита-Норд» — ревизия домофона на входе' },
  { t: 532, kind: 'Авария', text: 'P1 · Банк «Меридиан» — не открывается СКУД на входе', moved: 3, aff: ['e2', 'e9'] },
  { t: 545, kind: 'Отмена', text: 'Клиника «Здоровье+» отменила визит: перенос на завтра', moved: 1, aff: ['e4'] },
  { t: 558, kind: 'Новая заявка', text: 'P3 · Школа № 1298 — точка Wi-Fi в актовом зале' },
  { t: 571, kind: 'Визит затянулся', text: 'Титов на монтаже камер: +35 мин, юстировка сложнее' },
  { t: 587, kind: 'Новая заявка', text: 'P2 · БЦ «Аврора Плаза» — доступ к серверной для аренды' },
  { t: 602, kind: 'Больничный', text: 'Громов снят со смены с 12:00 — 2 визита переназначены', moved: 2, aff: ['e13', 'e3', 'e8'] },
  { t: 615, kind: 'Новая заявка', text: 'P4 · Типография «Литера» — обжим патч-кордов в кроссе' },
  { t: 629, kind: 'Визит затянулся', text: 'Орлов на заправке кондиционера: +15 мин, доступ к крыше' },
  { t: 644, kind: 'Авария', text: 'P1 · ООО «Фудмаркет Юг» — обесточена касса, ККТ молчит', moved: 2, aff: ['e11'] },
  { t: 658, kind: 'Новая заявка', text: 'P3 · Гостиница «Пресня» — ремонт вызывной панели' },
  { t: 672, kind: 'Поломка машины', text: 'Фургон Козлова в сервисе до 15:00 — маршрут пересобран', moved: 3, aff: ['e2', 'e12'] },
  { t: 687, kind: 'Новая заявка', text: 'P3 · Салон «Оптика Сити» — камера над кассой без сигнала' },
  { t: 700, kind: 'Отмена', text: 'ООО «МедиаСофт» перенёс визит: нет доступа в серверную', moved: 1, aff: ['e8'] },
  { t: 715, kind: 'Новая заявка', text: 'P4 · Фитнес-клуб «Тонус» — замер изоляции в щитовой' },
  { t: 730, kind: 'Визит затянулся', text: 'Виноградов на сварке ВОЛС: +25 мин, муфта в колодце' },
  { t: 746, kind: 'Новая заявка', text: 'P2 · АО «ТехноРитейл» — СКС в новом торговом зале' },
  { t: 761, kind: 'Авария', text: 'P1 · Каширское ш., 24 — сработка пожарной сигнализации', moved: 4, aff: ['e7', 'e4'] },
  { t: 777, kind: 'Новая заявка', text: 'P3 · ООО «Дента-Люкс» — переезд ККТ на новую стойку' },
  { t: 795, kind: 'Визит затянулся', text: 'Морозов на коммутации стойки: +30 мин, докупка патч-корда' },
  { t: 818, kind: 'Новая заявка', text: 'P4 · ООО «Логистика-М» — трассировка кабеля на складе' },
  { t: 842, kind: 'Отмена', text: 'Школа № 1298 отменила Wi-Fi: перенос на каникулы', moved: 1, aff: ['e6'] },
  { t: 867, kind: 'Новая заявка', text: 'P3 · БЦ «Аврора Плаза» — камера в паркинге не пишет' },
  { t: 891, kind: 'Авария', text: 'P1 · ТЦ «Гагаринский» — лёг узел Wi-Fi в фуд-корте', moved: 2, aff: ['e6', 'e18'] },
];

export const EFFECT = [
  { name: 'Закрыто в срок', ours: '49 из 52', manual: '41 из 46', better: true, main: true },
  { name: 'Нарушений SLA', ours: '3', manual: '1', better: false, note: 'У ручного плана меньше потому, что он не взял 6 неудобных заявок вовсе' },
  { name: 'Заявок взято в план', ours: '52 из 52', manual: '46 из 52', better: true },
  { name: 'Время в пути, суммарно', ours: '41 ч 06 мин', manual: '52 ч 40 мин', better: true },
  { name: 'Пробег, км', ours: '618', manual: '794', better: true },
  { name: 'Простой в ожидании', ours: '3 ч 34 мин', manual: '7 ч 48 мин', better: true },
  { name: 'Разброс загрузки', ours: '177–485 мин', manual: '96–540 мин', better: true },
];

export const DATA = { engineers: ENGINEERS, jobs: JOBS, events: EVENTS, effect: EFFECT, worktypes: WORK_TYPES, equipment: EQUIPMENT, warehouses: WAREHOUSES, unassigned: UNASSIGNED };
