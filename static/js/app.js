const state = {
  data: null,
  currentView: 'dashboard',
  currentPeriodId: 'per-2026-03',
  currentUserId: null,
  filters: { activitySearch: '', activityStatus: 'Todos', commitmentStatus: 'Todos' }
};

const viewLabels = { dashboard: 'Panel general', activities: 'Actividades', evidence: 'Evidencias', agenda: 'Agenda colectiva', reports: 'Reportes', periods: 'Periodo', adjustments: 'Bonificaciones y penalizaciones', admin: 'Administración' };
const roleViews = {
  Funcionario: ['dashboard', 'activities', 'evidence', 'agenda', 'reports'],
  Supervisor: ['dashboard', 'evidence', 'reports', 'adjustments'],
  Coordinador: ['dashboard', 'activities', 'evidence', 'agenda', 'reports', 'periods', 'adjustments', 'admin'],
  Delegado: ['dashboard', 'activities', 'evidence', 'agenda', 'reports', 'adjustments'],
  Admin: ['dashboard', 'periods', 'admin'],
  Verificador: ['dashboard', 'evidence', 'reports', 'adjustments'],
  Usuario: ['dashboard', 'reports']
};
const dateFormatter = new Intl.DateTimeFormat('es-CL', { day: '2-digit', month: 'short', year: 'numeric' });
const numberFormatter = new Intl.NumberFormat('es-CL', { maximumFractionDigits: 1 });

const byId = (id) => document.getElementById(id);
const currentUser = () => state.data.users.find((user) => user.id === state.currentUserId);
const currentPeriod = () => state.data.periods.find((period) => period.id === state.currentPeriodId);
const getUser = (id) => state.data.users.find((user) => user.id === id) || { name: 'Usuario desconocido', initials: '??' };
const getItem = (id) => state.data.items.find((item) => item.id === id) || { name: 'Ítem no disponible', shortName: 'Sin ítem', target: 0, weight: 0, unit: 'unidades' };
const getDelegation = (id) => state.data.delegations.find((delegation) => delegation.id === id) || { name: 'Delegación no disponible' };
const allowedViews = () => roleViews[currentUser()?.role] || roleViews.Usuario;
const canAccessView = (view) => allowedViews().includes(view);
const periodDays = (period) => Math.max(1, Math.round((new Date(`${period.end}T12:00:00`) - new Date(`${period.start}T12:00:00`)) / 86400000) + 1);
const formatDate = (value) => value ? dateFormatter.format(new Date(`${value}T12:00:00`)) : 'Sin fecha';
const formatDateTime = (value) => value ? new Intl.DateTimeFormat('es-CL', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(value)) : 'Sin fecha';
const escapeHtml = (value = '') => String(value).replace(/[&<>'"]/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#039;', '"': '&quot;' }[char]));
const statusClass = (status) => ({ Aprobada: 'badge-approved', Validada: 'badge-approved', Pendiente: 'badge-pending', 'Pendiente de validación': 'badge-pending', Rechazada: 'badge-rejected', Observada: 'badge-rejected', 'En proceso': 'badge-process', Realizado: 'badge-approved', Ingresado: 'badge-closed' }[status] || 'badge-closed');
const statusBadge = (status) => `<span class="badge-soft ${statusClass(status)}">${escapeHtml(status)}</span>`;

function approvedActivities(userId = null) {
  return state.data.activities.filter((activity) => activity.periodId === state.currentPeriodId && activity.status === 'Validada' && (!userId || activity.userId === userId));
}

function getMetrics(userId = null) {
  const activities = approvedActivities(userId);
  const byItem = state.data.items.map((item) => {
    const advance = activities.filter((activity) => activity.itemId === item.id).length;
    const rawCompliance = item.target > 0 ? (advance / item.target) * 100 : 0;
    const compliance = Math.min(rawCompliance, state.data.parameters.maxCompliance);
    return { ...item, advance, compliance, weighted: (item.weight * compliance) / 100 };
  });
  const weighted = byItem.reduce((sum, item) => sum + item.weighted, 0);
  const period = currentPeriod();
  const start = new Date(`${period.start}T12:00:00`);
  const end = new Date(`${period.end}T12:00:00`);
  const today = new Date();
  const effectiveDate = today < start ? start : today > end ? end : today;
  const totalDays = Math.max(1, Math.round((end - start) / 86400000) + 1);
  const elapsedDays = Math.max(0, Math.round((effectiveDate - start) / 86400000) + 1);
  const expected = Math.min(100, (elapsedDays / totalDays) * 100);
  const real = byItem.reduce((sum, item) => sum + item.compliance, 0) / Math.max(1, byItem.length);
  const ratio = expected > 0 ? real / expected : 1;
  const traffic = ratio >= 1 ? 'green' : ratio >= state.data.parameters.amberRatio / 100 ? 'amber' : 'red';
  return { byItem, weighted, expected, real, traffic, activities: activities.length };
}

function renderApp() {
  if (!canAccessView(state.currentView)) state.currentView = 'dashboard';
  updateUserChrome();
  byId('currentViewLabel').textContent = viewLabels[state.currentView];
  document.querySelectorAll('.nav-link').forEach((button) => { const visible = canAccessView(button.dataset.view); button.hidden = !visible; button.classList.toggle('active', button.dataset.view === state.currentView); });
  const renderers = { dashboard: renderDashboard, activities: renderActivities, evidence: renderEvidence, agenda: renderAgenda, reports: renderReports, periods: renderPeriods, adjustments: renderAdjustments, admin: renderAdmin };
  byId('appContent').innerHTML = renderers[state.currentView]();
  bindViewEvents();
}

function updateUserChrome() {
  const user = currentUser();
  byId('sidebarUser').textContent = user.name;
  byId('sidebarRole').textContent = user.roleLabel;
  document.querySelectorAll('.avatar').forEach((avatar) => { avatar.textContent = user.initials; });
  const pendingEvidence = state.data.evidences.filter((evidence) => evidence.status === 'Pendiente').length;
  byId('activityCount').textContent = state.data.activities.length;
  byId('evidenceCount').textContent = pendingEvidence;
}

function renderDashboard() {
  const user = currentUser();
  const metrics = getMetrics(user.role === 'Funcionario' ? user.id : null);
  const commitments = state.data.commitments.filter((commitment) => commitment.periodId === state.currentPeriodId);
  const delegationUsers = state.data.users.filter((candidate) => candidate.delegationId === user.delegationId && candidate.role === 'Funcionario');
  const trafficLabel = { green: 'En ritmo esperado', amber: 'Requiere seguimiento', red: 'Bajo el ritmo esperado' }[metrics.traffic];
  return `<div class="page-heading"><div><div class="eyebrow mb-2">${escapeHtml(currentPeriod().name).toUpperCase()}</div><h1>Buenos días, ${escapeHtml(user.name.split(' ')[0])}</h1><p>Una vista clara para acompañar el trabajo de tu delegación.</p></div><div class="date-stamp"><i class="bi bi-calendar3 me-1"></i> Actualizado hoy, 22 de septiembre de 2026</div></div>
    <div class="kpi-grid"><div class="kpi-card"><div class="kpi-label"><i class="bi bi-activity"></i> Avance aprobado</div><div class="kpi-value">${metrics.activities}<span class="fs-6 fw-normal text-secondary"> registros</span></div><div class="kpi-meta"><span class="kpi-trend"><i class="bi bi-arrow-up-right"></i> 12%</span> vs. período anterior</div></div>
    <div class="kpi-card"><div class="kpi-label"><i class="bi bi-bullseye"></i> Cumplimiento promedio</div><div class="kpi-value">${numberFormatter.format(metrics.real)}<span class="fs-6 fw-normal text-secondary">%</span></div><div class="kpi-meta">Meta esperada: <strong>${numberFormatter.format(metrics.expected)}%</strong></div></div>
    <div class="kpi-card"><div class="kpi-label"><i class="bi bi-layers"></i> Resultado ponderado</div><div class="kpi-value">${numberFormatter.format(metrics.weighted)}<span class="fs-6 fw-normal text-secondary">%</span></div><div class="kpi-meta">Ponderadores configurados: <strong>100%</strong></div></div>
    <div class="kpi-card"><div class="kpi-label"><i class="bi bi-signpost-split"></i> Estado general</div><div class="kpi-value traffic-value ${metrics.traffic}">${trafficLabel}</div><div class="kpi-meta">Umbral colectivo: <strong>${state.data.parameters.collectiveThreshold}%</strong></div></div></div>
    <section class="panel mb-4"><div class="panel-header"><div><h2 class="panel-title">Semáforo de cumplimiento diario</h2><div class="panel-subtitle">Comparación entre cumplimiento real y meta esperada del personal autorizado</div></div>${statusBadge(trafficLabel)}</div><div class="panel-body"><div class="traffic-panel ${metrics.traffic}"><span class="traffic-light"></span><div><strong>${trafficLabel}</strong><p class="mb-0">Cumplimiento real: ${numberFormatter.format(metrics.real)}% · Meta esperada al día: ${numberFormatter.format(metrics.expected)}%</p></div></div></div></section>
    <div class="dashboard-grid"><section class="panel chart-panel"><div class="panel-header"><div><h2 class="panel-title">Avance de la delegación</h2><div class="panel-subtitle">Registros validados por semana · ${escapeHtml(getDelegation(user.delegationId).name)}</div></div><button class="btn btn-sm btn-light-border" data-view-action="reports">Ver reporte <i class="bi bi-arrow-up-right ms-1"></i></button></div><div class="panel-body">${renderBars(metrics)}<div class="legend-row"><span><i class="legend-dot"></i> Avance real</span><span><i class="legend-dot expected"></i> Meta acumulada</span></div></div></section>
    <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Estado de compromisos</h2><div class="panel-subtitle">Agenda colectiva del período actual</div></div><button class="btn btn-sm btn-link text-decoration-none p-0" data-view-action="agenda">Ver agenda</button></div><div class="panel-body"><div class="status-list">${renderCommitmentStatus(commitments)}</div></div></section></div>
    <section class="panel table-panel"><div class="panel-header"><div><h2 class="panel-title">Desempeño por ítem</h2><div class="panel-subtitle">Detalle de indicadores y evidencia de origen</div></div><button class="btn btn-sm btn-light-border" data-view-action="activities">Ver actividades</button></div><div class="panel-body"><div class="table-responsive"><table class="table"><thead><tr><th>Ítem medido</th><th>Meta</th><th>Avance</th><th>Cumplimiento</th><th>Ponderación</th><th>Estado</th></tr></thead><tbody>${metrics.byItem.map((item) => `<tr><td><strong>${escapeHtml(item.shortName)}</strong><small class="d-block text-secondary mt-1">${escapeHtml(item.name)}</small></td><td>${item.target} ${escapeHtml(item.unit)}</td><td>${item.advance}</td><td><div class="d-flex align-items-center gap-2"><div class="progress progress-thin"><div class="progress-bar" style="width:${Math.min(item.compliance, 100)}%"></div></div><span>${numberFormatter.format(item.compliance)}%</span></div></td><td>${item.weight}%</td><td>${item.compliance >= 100 ? statusBadge('Cumplida') : statusBadge('En seguimiento')}</td></tr>`).join('')}</tbody></table></div></div></section>
    <section class="panel table-panel"><div class="panel-header"><div><h2 class="panel-title">Actividad reciente</h2><div class="panel-subtitle">Últimos movimientos del equipo</div></div><span class="badge-soft badge-process">${delegationUsers.length} funcionarios activos</span></div><div class="panel-body"><div class="table-responsive"><table class="table"><thead><tr><th>Fecha</th><th>Actividad</th><th>Responsable</th><th>Evidencia</th><th>Estado</th></tr></thead><tbody>${state.data.activities.slice().sort((a,b) => b.date.localeCompare(a.date)).slice(0, 4).map((activity) => `<tr><td>${formatDate(activity.date)}</td><td><strong>${escapeHtml(activity.description)}</strong><small class="d-block text-secondary mt-1">${escapeHtml(activity.code)}</small></td><td>${escapeHtml(getUser(activity.userId).name)}</td><td><i class="bi bi-paperclip text-teal"></i> ${escapeHtml(activity.code)}</td><td>${statusBadge(activity.status)}</td></tr>`).join('')}</tbody></table></div></div></section>`;
}

function renderBars(metrics) {
  const values = [42, 55, 47, 71, 64, Math.max(38, Math.round(metrics.real))];
  const labels = ['19 ago', '26 ago', '02 sep', '09 sep', '16 sep', 'Hoy'];
  return `<div class="chart-area">${values.map((value, index) => `<div class="bar-column"><div class="bar" data-value="${value}%" style="height:${value}%"></div><span class="bar-label">${labels[index]}</span></div>`).join('')}</div>`;
}

function renderCommitmentStatus(commitments) {
  const counts = { Realizado: 0, 'En proceso': 0, Pendiente: 0, Vencido: 0 };
  commitments.forEach((commitment) => { const overdue = commitment.status !== 'Realizado' && commitment.dueDate < '2026-09-22'; counts[overdue ? 'Vencido' : commitment.status] = (counts[overdue ? 'Vencido' : commitment.status] || 0) + 1; });
  return [['green', 'Realizados', counts.Realizado, 'Cerrados en el período'], ['amber', 'En proceso', counts['En proceso'], 'Con seguimiento activo'], ['red', 'Vencidos', counts.Vencido, 'Requieren atención']].map(([color, label, count, detail]) => `<div class="status-row"><span class="status-dot ${color}"></span><div><strong>${label}</strong><small>${detail}</small></div><b>${count}</b></div>`).join('');
}

function renderActivities() {
  const filtered = state.data.activities.filter((activity) => {
    const search = state.filters.activitySearch.toLowerCase();
    const matchesSearch = !search || `${activity.description} ${activity.code} ${activity.contact}`.toLowerCase().includes(search);
    const matchesStatus = state.filters.activityStatus === 'Todos' || activity.status === state.filters.activityStatus;
    return matchesSearch && matchesStatus && activity.periodId === state.currentPeriodId;
  });
  return `<div class="page-heading"><div><div class="eyebrow mb-2">OPERACIÓN PRINCIPAL</div><h1>Actividades</h1><p>Registra, clasifica y consulta el trabajo ejecutado por el equipo.</p></div><button class="btn btn-primary" data-action="open-activity"><i class="bi bi-plus-lg me-2"></i>Registrar actividad</button></div>
    <div class="filter-bar"><div class="input-group search-box"><span class="input-group-text bg-white border-end-0"><i class="bi bi-search text-secondary"></i></span><input class="form-control border-start-0" id="activitySearch" value="${escapeHtml(state.filters.activitySearch)}" placeholder="Buscar por descripción, código o contacto" aria-label="Buscar actividades"></div><select class="form-select" id="activityStatusFilter" style="max-width:190px"><option>Todos</option><option>Pendiente de validación</option><option>Validada</option><option>Observada</option></select><button class="btn btn-light-border" data-action="export-activities"><i class="bi bi-download me-1"></i>Exportar</button></div>
    <div class="d-flex justify-content-between align-items-center mb-3"><span class="text-secondary small">${filtered.length} registros encontrados</span><span class="text-secondary small">Período: <strong>${escapeHtml(currentPeriod().name)}</strong></span></div>${filtered.length ? filtered.map(renderActivityCard).join('') : renderEmpty('bi-search', 'No hay actividades para estos filtros', 'Prueba con otro término o estado.')}`;
}

function renderActivityCard(activity) {
  const item = getItem(activity.itemId);
  return `<article class="activity-card"><div><div class="activity-code">${escapeHtml(activity.code)}</div><h3>${escapeHtml(activity.description)}</h3><p>${escapeHtml(activity.action)}</p><div class="activity-meta"><span><i class="bi bi-calendar3"></i>${formatDate(activity.date)}</span><span><i class="bi bi-person"></i>${escapeHtml(getUser(activity.userId).name)}</span><span><i class="bi bi-tag"></i>${escapeHtml(item.shortName)}</span><span><i class="bi bi-geo-alt"></i>${escapeHtml(getDelegation(activity.delegationId).name)}</span></div></div><div class="activity-side">${statusBadge(activity.status)}<div class="action-row"><button class="btn-icon" title="Ver detalle" data-action="view-activity" data-id="${activity.id}"><i class="bi bi-eye"></i></button>${activity.status === 'Pendiente de validación' ? `<button class="btn-icon" title="Ir a evidencias" data-action="go-evidence"><i class="bi bi-patch-check"></i></button>` : ''}</div></div></article>`;
}

function renderEvidence() {
  const evidences = state.data.evidences.filter((evidence) => state.data.activities.find((activity) => activity.id === evidence.activityId)?.periodId === state.currentPeriodId);
  const pending = evidences.filter((evidence) => evidence.status === 'Pendiente').length;
  return `<div class="page-heading"><div><div class="eyebrow mb-2">CONTROL Y VERIFICACIÓN</div><h1>Evidencias</h1><p>Revisa los respaldos asociados a las actividades y decide qué aporta al resultado.</p></div><div class="date-stamp"><span class="badge-soft badge-pending"><i class="bi bi-hourglass-split me-1"></i>${pending} pendientes de revisión</span></div></div>${pending ? `<div class="alert-box amber"><i class="bi bi-exclamation-circle"></i><span>Hay ${pending} evidencia pendiente. La aprobación recalculará automáticamente el indicador asociado.</span></div>` : ''}<div class="evidence-grid">${evidences.map(renderEvidenceCard).join('')}</div>`;
}

function renderEvidenceCard(evidence) {
  const activity = state.data.activities.find((candidate) => candidate.id === evidence.activityId);
  const replacement = evidence.status === 'Rechazada' ? `<button class="btn btn-sm btn-teal w-100 mt-3" data-action="replace-evidence" data-id="${evidence.id}"><i class="bi bi-upload me-1"></i>Subir nueva evidencia</button>` : '';
  const actions = evidence.status === 'Pendiente' ? `<div class="d-flex gap-2 mt-3"><button class="btn btn-sm btn-teal flex-grow-1" data-action="validate-evidence" data-id="${evidence.id}" data-decision="Aprobada"><i class="bi bi-check2 me-1"></i>Aprobar</button><button class="btn btn-sm btn-light-border" data-action="validate-evidence" data-id="${evidence.id}" data-decision="Rechazada" title="Rechazar evidencia"><i class="bi bi-x-lg"></i></button></div>` : `${replacement}<button class="btn btn-sm btn-light-border w-100 mt-2" data-action="view-activity" data-id="${activity.id}"><i class="bi bi-arrow-up-right me-1"></i>Ver actividad</button>`;
  return `<article class="evidence-card"><div class="evidence-icon"><i class="bi ${evidence.type.includes('pdf') ? 'bi-file-earmark-pdf' : 'bi-image'}"></i></div><div class="d-flex justify-content-between align-items-start gap-2"><div><h3>${escapeHtml(evidence.fileName)}</h3><p>${escapeHtml(activity.description)}</p></div>${statusBadge(evidence.status)}</div><div class="evidence-detail"><span><span>Código</span><b>${escapeHtml(activity.code)}</b></span><span><span>Cargada por</span><b>${escapeHtml(getUser(evidence.uploadedBy).name)}</b></span><span><span>Fecha</span><b>${formatDateTime(evidence.uploadedAt)}</b></span>${evidence.comment ? `<span><span>Observación</span><b>${escapeHtml(evidence.comment)}</b></span>` : ''}</div>${actions}</article>`;
}

function renderAgenda() {
  const commitments = state.data.commitments.filter((commitment) => commitment.periodId === state.currentPeriodId && (state.filters.commitmentStatus === 'Todos' || commitment.status === state.filters.commitmentStatus));
  const overdue = commitments.filter((commitment) => commitment.status !== 'Realizado' && commitment.dueDate < '2026-09-22');
  return `<div class="page-heading"><div><div class="eyebrow mb-2">COORDINACIÓN OPERATIVA</div><h1>Agenda colectiva</h1><p>Seguimiento de compromisos, responsables y fechas de cumplimiento.</p></div><button class="btn btn-primary" data-action="open-commitment"><i class="bi bi-plus-lg me-2"></i>Nuevo compromiso</button></div><div class="agenda-layout"><section class="panel"><div class="panel-header"><div><h2 class="panel-title">Tubo de trabajo</h2><div class="panel-subtitle">${commitments.length} compromisos del período</div></div><select class="form-select form-select-sm" id="commitmentStatusFilter" style="width:auto"><option>Todos</option><option>Ingresado</option><option>Pendiente</option><option>En proceso</option><option>Realizado</option></select></div><div class="panel-body">${commitments.length ? commitments.map(renderCommitment).join('') : renderEmpty('bi-calendar-x', 'No hay compromisos', 'Crea un compromiso o cambia el filtro.')}</div></section><aside><div class="alert-box red"><i class="bi bi-alarm"></i><span><strong>${overdue.length} vencido${overdue.length === 1 ? '' : 's'}</strong><br>Revisa los compromisos sin cierre.</span></div><div class="panel"><div class="panel-header"><div><h2 class="panel-title">Estados</h2><div class="panel-subtitle">Distribución actual</div></div></div><div class="panel-body"><div class="status-list">${renderCommitmentStatus(commitments)}</div></div></div></aside></div>`;
}

function renderCommitment(commitment) {
  const overdue = commitment.status !== 'Realizado' && commitment.dueDate < '2026-09-22';
  return `<div class="commitment-row"><div><h3>${escapeHtml(commitment.description)}</h3><p>${escapeHtml(commitment.requester)} · ${escapeHtml(commitment.territory)}</p><div class="commitment-meta"><span><i class="bi bi-person me-1"></i>${escapeHtml(getUser(commitment.responsibleId).name)}</span><span><i class="bi bi-building me-1"></i>${escapeHtml(commitment.supportArea)}</span><span class="${overdue ? 'text-danger fw-bold' : ''}"><i class="bi bi-calendar3 me-1"></i>${formatDate(commitment.dueDate)}${overdue ? ' · vencido' : ''}</span></div></div><div class="commitment-actions">${statusBadge(overdue ? 'Vencido' : commitment.status)}<button class="btn-icon" title="Actualizar estado" data-action="update-commitment" data-id="${commitment.id}"><i class="bi bi-arrow-repeat"></i></button></div></div>`;
}

function renderReports() {
  const metrics = getMetrics();
  return `<div class="page-heading"><div><div class="eyebrow mb-2">INFORMACIÓN PARA DECIDIR</div><h1>Reportes</h1><p>Consulta información consolidada y exporta el detalle del período.</p></div><button class="btn btn-primary" data-action="export-activities"><i class="bi bi-download me-2"></i>Exportar actividades</button></div><div class="row g-3 mb-4"><div class="col-md-4"><div class="panel report-card"><div class="evidence-icon"><i class="bi bi-graph-up-arrow"></i></div><h3>Resumen de gestión</h3><p>Consolidado de avance, cumplimiento y resultado ponderado de la delegación seleccionada.</p><button class="btn btn-sm btn-light-border" data-action="show-report" data-report="summary">Ver resumen <i class="bi bi-arrow-right ms-1"></i></button></div></div><div class="col-md-4"><div class="panel report-card"><div class="evidence-icon"><i class="bi bi-calendar2-check"></i></div><h3>Compromisos y plazos</h3><p>${state.data.commitments.filter((commitment) => commitment.status !== 'Realizado').length} compromisos requieren seguimiento en el período vigente.</p><button class="btn btn-sm btn-light-border" data-view-action="agenda">Revisar agenda <i class="bi bi-arrow-right ms-1"></i></button></div></div><div class="col-md-4"><div class="panel report-card"><div class="evidence-icon"><i class="bi bi-shield-check"></i></div><h3>Trazabilidad</h3><p>Consulta las operaciones críticas registradas durante la demostración del sistema.</p><button class="btn btn-sm btn-light-border" data-view-action="admin">Ver auditoría <i class="bi bi-arrow-right ms-1"></i></button></div></div></div><section class="panel"><div class="panel-header"><div><h2 class="panel-title">Indicadores consolidados</h2><div class="panel-subtitle">Valores calculados desde los registros aprobados</div></div></div><div class="panel-body"><div class="table-responsive"><table class="table"><thead><tr><th>Indicador</th><th>Valor actual</th><th>Regla aplicada</th><th>Resultado</th></tr></thead><tbody><tr><td>Avance aprobado</td><td>${metrics.activities} registros</td><td>Actividades con evidencia aprobada</td><td>${statusBadge('Validada')}</td></tr><tr><td>Cumplimiento promedio</td><td>${numberFormatter.format(metrics.real)}%</td><td>Avance / meta x 100</td><td>${statusBadge(metrics.traffic === 'green' ? 'Cumplida' : 'En seguimiento')}</td></tr><tr><td>Meta esperada al día</td><td>${numberFormatter.format(metrics.expected)}%</td><td>Días transcurridos / días totales x 100</td><td>${statusBadge('En proceso')}</td></tr><tr><td>Resultado ponderado</td><td>${numberFormatter.format(metrics.weighted)}%</td><td>Ponderador x cumplimiento / 100</td><td>${statusBadge('Validada')}</td></tr></tbody></table></div></div></section>`;
}

function renderPeriods() {
  return `<div class="page-heading"><div><div class="eyebrow mb-2">CONFIGURACIÓN DE MEDICIÓN</div><h1>Periodo</h1><p>Consulta las fechas y los días computables calculados para cada período.</p></div></div><section class="panel"><div class="panel-header"><div><h2 class="panel-title">Períodos de medición</h2><div class="panel-subtitle">El cálculo incluye la fecha inicial y final</div></div></div><div class="panel-body"><div class="table-responsive"><table class="table"><thead><tr><th>Período</th><th>Inicio</th><th>Término</th><th>Días computables</th><th>Estado</th></tr></thead><tbody>${state.data.periods.map((period) => `<tr><td><strong>${escapeHtml(period.name)}</strong></td><td>${formatDate(period.start)}</td><td>${formatDate(period.end)}</td><td><strong>${periodDays(period)}</strong> días</td><td>${statusBadge(period.status)}</td></tr>`).join('')}</tbody></table></div></div></section>`;
}

function renderAdjustments() {
  const adjustments = state.data.adjustments || [];
  return `<div class="page-heading"><div><div class="eyebrow mb-2">MEDICIÓN Y RECONOCIMIENTO</div><h1>Bonificaciones y penalizaciones</h1><p>Registra felicitaciones y reclamos que ajustan el cumplimiento del período.</p></div><button class="btn btn-primary" data-action="add-adjustment"><i class="bi bi-plus-lg me-2"></i>Agregar ajuste</button></div><section class="panel"><div class="panel-header"><div><h2 class="panel-title">Ajustes del período</h2><div class="panel-subtitle">El porcentaje queda editable para parametrización posterior</div></div></div><div class="panel-body"><div class="table-responsive"><table class="table"><thead><tr><th>Tipo</th><th>Descripción</th><th>Responsable</th><th>Porcentaje</th><th>Estado</th></tr></thead><tbody>${adjustments.length ? adjustments.map((adjustment) => `<tr><td>${adjustment.type === 'Bonificación' ? '<span class="badge-soft badge-approved">Bonificación</span>' : '<span class="badge-soft badge-rejected">Penalización</span>'}</td><td>${escapeHtml(adjustment.description)}</td><td>${escapeHtml(getUser(adjustment.userId).name)}</td><td><input class="form-control form-control-sm adjustment-value" type="number" step="0.1" value="${adjustment.percent ?? ''}" placeholder="%" data-id="${adjustment.id}" aria-label="Porcentaje del ajuste"></td><td>${statusBadge(adjustment.status)}</td></tr>`).join('') : `<tr><td colspan="5">${renderEmpty('bi-award', 'No hay ajustes registrados', 'Agrega una felicitación o reclamo para este período.')}</td></tr>`}</tbody></table></div></div></section>`;
}

function renderAdmin() {
  const totalWeight = state.data.items.reduce((sum, item) => sum + item.weight, 0);
  return `<div class="page-heading"><div><div class="eyebrow mb-2">CONFIGURACIÓN Y CONTROL</div><h1>Administración</h1><p>Parámetros, perfiles y trazabilidad del entorno de demostración.</p></div><span class="badge-soft badge-process"><i class="bi bi-shield-check me-1"></i>Modo demostración</span></div><div class="admin-grid mb-4"><div class="setting-card"><h3><i class="bi bi-people me-2 text-teal"></i>Usuarios y roles</h3><p>${state.data.users.length} perfiles ficticios con ámbitos diferenciados.</p><button class="btn btn-sm btn-light-border" data-action="switch-profile">Cambiar perfil</button></div><div class="setting-card"><h3><i class="bi bi-sliders me-2 text-teal"></i>Parámetros de medición</h3><p>Tope ${state.data.parameters.maxCompliance}% · Umbral colectivo ${state.data.parameters.collectiveThreshold}% · Ponderación ${totalWeight}%.</p><button class="btn btn-sm btn-light-border" data-action="show-parameters">Editar parámetros</button></div><div class="setting-card"><h3><i class="bi bi-clock-history me-2 text-teal"></i>Períodos</h3><p>${state.data.periods.length} períodos configurados, uno abierto y uno cerrado.</p><button class="btn btn-sm btn-light-border" data-action="show-periods">Ver períodos</button></div></div><section class="panel"><div class="panel-header"><div><h2 class="panel-title">Auditoría de operaciones</h2><div class="panel-subtitle">Registro visible de acciones críticas del mock-up</div></div><button class="btn btn-sm btn-light-border" data-action="show-audit-info"><i class="bi bi-info-circle me-1"></i>Sobre auditoría</button></div><div class="panel-body"><div class="table-responsive"><table class="table audit-table"><thead><tr><th>Fecha</th><th>Acción</th><th>Entidad</th><th>Usuario</th><th>Detalle</th></tr></thead><tbody>${state.data.audit.slice().sort((a,b) => b.date.localeCompare(a.date)).map((entry) => `<tr><td>${formatDateTime(entry.date)}</td><td><strong>${escapeHtml(entry.action)}</strong></td><td>${escapeHtml(entry.entity)} · ${escapeHtml(entry.entityId)}</td><td>${escapeHtml(getUser(entry.userId).name)}</td><td>${escapeHtml(entry.detail)}</td></tr>`).join('')}</tbody></table></div></div></section>`;
}

function renderEmpty(icon, title, text) { return `<div class="empty-state"><i class="bi ${icon}"></i><strong>${title}</strong><div class="small mt-1">${text}</div></div>`; }

function openActivityModal(activity = null) {
  const modal = byId('activityModalContent');
  modal.innerHTML = `<div class="modal-header"><h2 class="modal-title" id="activityModalLabel">${activity ? 'Detalle de actividad' : 'Registrar actividad'}</h2><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button></div>${activity ? renderActivityDetail(activity) : `<form id="activityForm"><div class="modal-body"><div class="alert-box amber mb-4"><i class="bi bi-lightbulb"></i><span>Al guardar se generará un código único e inmutable para vincular la evidencia.</span></div><div class="row g-3"><div class="col-md-4"><label class="form-label" for="activityDate">Fecha de actividad *</label><input class="form-control" type="date" id="activityDate" value="2026-09-22" required></div><div class="col-md-8"><label class="form-label" for="activityItem">Ítem de medición *</label><select class="form-select" id="activityItem" required><option value="">Selecciona un ítem</option>${state.data.items.map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join('')}</select></div><div class="col-12"><label class="form-label" for="activityDescription">Actividad, solicitud o problema *</label><input class="form-control" id="activityDescription" required maxlength="120" placeholder="Describe brevemente la gestión realizada"></div><div class="col-12"><label class="form-label" for="activityAction">Acción ejecutada *</label><textarea class="form-control" id="activityAction" rows="3" required maxlength="300" placeholder="Indica qué se hizo y cuál fue el resultado"></textarea></div><div class="col-md-7"><label class="form-label" for="activityContact">Contacto o referencia</label><input class="form-control" id="activityContact" maxlength="80" placeholder="Ej: Caso ficticio A-210"></div><div class="col-md-5"><label class="form-label" for="activityPhone">Teléfono</label><input class="form-control" id="activityPhone" pattern="[0-9 +()-]{7,18}" placeholder="Ej: 9 5555 0110"><div class="form-text">Solo datos ficticios.</div></div><div class="col-12"><div class="form-check"><input class="form-check-input" type="checkbox" id="activityAgenda"><label class="form-check-label small" for="activityAgenda">Relacionar también con la agenda colectiva</label></div></div></div></div><div class="modal-footer"><button type="button" class="btn btn-light-border" data-bs-dismiss="modal">Cancelar</button><button class="btn btn-primary" type="submit"><i class="bi bi-check2 me-1"></i>Guardar actividad</button></div></form>`}`;
  const bootstrapModal = bootstrap.Modal.getOrCreateInstance(byId('activityModal'));
  bootstrapModal.show();
  if (!activity) byId('activityForm').addEventListener('submit', handleActivitySubmit);
}

function renderActivityDetail(activity) {
  const evidence = state.data.evidences.find((candidate) => candidate.id === activity.evidenceId);
  return `<div class="modal-body"><div class="activity-code mb-2">${escapeHtml(activity.code)}</div><h3 class="mb-3">${escapeHtml(activity.description)}</h3><div class="row g-3 mb-4"><div class="col-md-6"><small class="text-secondary d-block">Fecha</small><strong>${formatDate(activity.date)}</strong></div><div class="col-md-6"><small class="text-secondary d-block">Responsable</small><strong>${escapeHtml(getUser(activity.userId).name)}</strong></div><div class="col-md-6"><small class="text-secondary d-block">Ítem</small><strong>${escapeHtml(getItem(activity.itemId).name)}</strong></div><div class="col-md-6"><small class="text-secondary d-block">Estado</small>${statusBadge(activity.status)}</div></div><div class="p-3 bg-light rounded-2 mb-3"><small class="text-secondary d-block mb-1">Acción ejecutada</small>${escapeHtml(activity.action)}</div><div class="p-3 border rounded-2"><div class="d-flex justify-content-between"><strong>Evidencia asociada</strong>${statusBadge(evidence?.status || 'Pendiente')}</div><div class="small text-secondary mt-2">${escapeHtml(evidence?.fileName || 'Sin archivo asociado')}</div>${evidence?.comment ? `<div class="small mt-2"><strong>Observación:</strong> ${escapeHtml(evidence.comment)}</div>` : ''}</div></div><div class="modal-footer"><button type="button" class="btn btn-light-border" data-bs-dismiss="modal">Cerrar</button></div>`;
}

function openCommitmentModal() {
  const modal = byId('commitmentModalContent');
  modal.innerHTML = `<div class="modal-header"><h2 class="modal-title" id="commitmentModalLabel">Nuevo compromiso</h2><button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Cerrar"></button></div><form id="commitmentForm"><div class="modal-body"><div class="row g-3"><div class="col-12"><label class="form-label" for="commitmentDescription">Compromiso *</label><input class="form-control" id="commitmentDescription" required maxlength="140" placeholder="Describe el resultado comprometido"></div><div class="col-md-6"><label class="form-label" for="commitmentRequester">Solicitante *</label><input class="form-control" id="commitmentRequester" required placeholder="Ej: Caso ficticio C-030"></div><div class="col-md-6"><label class="form-label" for="commitmentTerritory">Territorio *</label><input class="form-control" id="commitmentTerritory" required placeholder="Ej: La Serena rural"></div><div class="col-md-6"><label class="form-label" for="commitmentDueDate">Fecha comprometida *</label><input class="form-control" type="date" id="commitmentDueDate" required></div><div class="col-md-6"><label class="form-label" for="commitmentSupport">Área de apoyo *</label><select class="form-select" id="commitmentSupport" required><option value="">Selecciona un área</option><option>Obras Municipales</option><option>DIDECO</option><option>Medio Ambiente</option><option>Seguridad</option></select></div></div></div><div class="modal-footer"><button type="button" class="btn btn-light-border" data-bs-dismiss="modal">Cancelar</button><button class="btn btn-primary" type="submit"><i class="bi bi-check2 me-1"></i>Crear compromiso</button></div></form>`;
  bootstrap.Modal.getOrCreateInstance(byId('commitmentModal')).show();
  byId('commitmentForm').addEventListener('submit', handleCommitmentSubmit);
}

function bindViewEvents() {
  document.querySelectorAll('[data-view-action]').forEach((element) => element.addEventListener('click', () => { state.currentView = element.dataset.viewAction; renderApp(); }));
  document.querySelectorAll('[data-action="open-activity"]').forEach((element) => element.addEventListener('click', () => openActivityModal()));
  document.querySelectorAll('[data-action="open-commitment"]').forEach((element) => element.addEventListener('click', openCommitmentModal));
  document.querySelectorAll('[data-action="view-activity"]').forEach((element) => element.addEventListener('click', () => openActivityModal(state.data.activities.find((activity) => activity.id === element.dataset.id))));
  document.querySelectorAll('[data-action="go-evidence"]').forEach((element) => element.addEventListener('click', () => { state.currentView = 'evidence'; renderApp(); }));
  document.querySelectorAll('[data-action="validate-evidence"]').forEach((element) => element.addEventListener('click', () => handleEvidenceDecision(element.dataset.id, element.dataset.decision)));
  document.querySelectorAll('[data-action="replace-evidence"]').forEach((element) => element.addEventListener('click', () => replaceEvidence(element.dataset.id)));
  document.querySelectorAll('[data-action="update-commitment"]').forEach((element) => element.addEventListener('click', () => handleCommitmentUpdate(element.dataset.id)));
  document.querySelectorAll('[data-action="export-activities"]').forEach((element) => element.addEventListener('click', exportActivities));
  document.querySelectorAll('[data-action="switch-profile"]').forEach((element) => element.addEventListener('click', openProfilePicker));
  document.querySelectorAll('[data-action="show-parameters"]').forEach((element) => element.addEventListener('click', editParameters));
  document.querySelectorAll('[data-action="show-periods"]').forEach((element) => element.addEventListener('click', showPeriods));
  document.querySelectorAll('[data-action="show-audit-info"]').forEach((element) => element.addEventListener('click', showAuditInfo));
  document.querySelectorAll('[data-action="show-report"]').forEach((element) => element.addEventListener('click', () => Swal.fire({ title: 'Resumen listo', text: 'El reporte se ha preparado con los filtros del período vigente.', icon: 'success', confirmButtonColor: '#b92f1b' })));
  document.querySelectorAll('[data-action="add-adjustment"]').forEach((element) => element.addEventListener('click', addAdjustment));
  document.querySelectorAll('.adjustment-value').forEach((element) => element.addEventListener('change', (event) => updateAdjustment(event.target.dataset.id, event.target.value)));
  const activitySearch = byId('activitySearch'); if (activitySearch) activitySearch.addEventListener('input', (event) => { state.filters.activitySearch = event.target.value; renderApp(); const input = byId('activitySearch'); input.focus(); input.setSelectionRange(input.value.length, input.value.length); });
  const activityStatus = byId('activityStatusFilter'); if (activityStatus) { activityStatus.value = state.filters.activityStatus; activityStatus.addEventListener('change', (event) => { state.filters.activityStatus = event.target.value; renderApp(); }); }
  const commitmentStatus = byId('commitmentStatusFilter'); if (commitmentStatus) { commitmentStatus.value = state.filters.commitmentStatus; commitmentStatus.addEventListener('change', (event) => { state.filters.commitmentStatus = event.target.value; renderApp(); }); }
}

function handleActivitySubmit(event) {
  event.preventDefault();
  const form = event.target;
  if (!form.checkValidity()) { form.classList.add('was-validated'); Swal.fire({ title: 'Revisa el formulario', text: 'Completa los campos obligatorios antes de continuar.', icon: 'warning', confirmButtonColor: '#b92f1b' }); return; }
  const description = byId('activityDescription').value.trim();
  const date = byId('activityDate').value;
  if (date > '2026-09-22') { Swal.fire({ title: 'Fecha no válida', text: 'La fecha no puede ser posterior a la fecha actual de demostración.', icon: 'error', confirmButtonColor: '#b92f1b' }); return; }
  const nextNumber = 1000 + state.data.activities.length + 1;
  const activityId = `act-${nextNumber}`; const evidenceId = `ev-${nextNumber}`; const code = `SGR-2609-${nextNumber}`;
  state.data.activities.unshift({ id: activityId, code, date, description, action: byId('activityAction').value.trim(), contact: byId('activityContact').value.trim() || 'Sin referencia', phone: byId('activityPhone').value.trim() || 'No informado', itemId: byId('activityItem').value, userId: state.currentUserId, delegationId: currentUser().delegationId, periodId: state.currentPeriodId, evidenceId, status: 'Pendiente de validación', agenda: byId('activityAgenda').checked });
  state.data.evidences.unshift({ id: evidenceId, activityId, fileName: `${code}.jpg`, type: 'image/jpeg', size: 0, uploadedAt: new Date().toISOString(), uploadedBy: state.currentUserId, status: 'Pendiente', reviewerId: null, reviewedAt: null, comment: '' });
  state.data.audit.unshift({ id: `aud-${Date.now()}`, action: 'Registro de actividad', entity: 'Actividad', entityId: activityId, userId: state.currentUserId, date: new Date().toISOString(), detail: `Actividad creada con código ${code}` });
  bootstrap.Modal.getInstance(byId('activityModal')).hide(); renderApp();
  Swal.fire({ title: 'Actividad registrada', html: `Código generado: <strong>${code}</strong><br><small>Ya puedes asociar la evidencia desde la vista correspondiente.</small>`, icon: 'success', confirmButtonColor: '#b92f1b' });
}

async function handleEvidenceDecision(evidenceId, decision) {
  const evidence = state.data.evidences.find((candidate) => candidate.id === evidenceId);
  const activity = state.data.activities.find((candidate) => candidate.id === evidence.activityId);
  if (decision === 'Rechazada') {
    const result = await Swal.fire({ title: 'Rechazar evidencia', input: 'textarea', inputLabel: 'Motivo de la observación', inputPlaceholder: 'Indica qué debe corregirse...', inputValidator: (value) => !value.trim() ? 'La observación es obligatoria.' : undefined, showCancelButton: true, confirmButtonText: 'Rechazar', cancelButtonText: 'Cancelar', confirmButtonColor: '#b92f1b' });
    if (!result.isConfirmed) return;
    evidence.comment = result.value.trim();
  } else {
    const result = await Swal.fire({ title: '¿Aprobar evidencia?', text: 'La actividad aportará al avance una sola vez.', icon: 'question', showCancelButton: true, confirmButtonText: 'Sí, aprobar', cancelButtonText: 'Cancelar', confirmButtonColor: '#079b92' });
    if (!result.isConfirmed) return;
    evidence.comment = 'Evidencia validada correctamente.';
  }
  evidence.status = decision; evidence.reviewerId = state.currentUserId; evidence.reviewedAt = new Date().toISOString(); activity.status = decision === 'Aprobada' ? 'Validada' : 'Observada';
  state.data.audit.unshift({ id: `aud-${Date.now()}`, action: 'Validación de evidencia', entity: 'Evidencia', entityId: evidenceId, userId: state.currentUserId, date: new Date().toISOString(), detail: `Estado cambió a ${decision}` });
  renderApp(); Swal.fire({ title: decision === 'Aprobada' ? 'Evidencia aprobada' : 'Evidencia observada', text: decision === 'Aprobada' ? 'El indicador fue recalculado.' : 'La observación quedó registrada.', icon: decision === 'Aprobada' ? 'success' : 'info', confirmButtonColor: '#b92f1b' });
}

async function replaceEvidence(evidenceId) {
  const oldEvidence = state.data.evidences.find((candidate) => candidate.id === evidenceId);
  const activity = state.data.activities.find((candidate) => candidate.id === oldEvidence.activityId);
  const result = await Swal.fire({ title: 'Subir nueva evidencia', html: '<input id="replacementFile" class="swal2-file" type="file" accept="image/jpeg,image/png,application/pdf"><small class="d-block text-muted mt-2">Formatos permitidos: JPG, PNG o PDF. Máximo 5 MB.</small>', focusConfirm: false, showCancelButton: true, confirmButtonText: 'Adjuntar', cancelButtonText: 'Cancelar', confirmButtonColor: '#079b92', preConfirm: () => { const file = document.getElementById('replacementFile').files[0]; if (!file) { Swal.showValidationMessage('Selecciona un archivo.'); return false; } if (!state.data.parameters.allowedEvidenceTypes.includes(file.type)) { Swal.showValidationMessage('El formato del archivo no está permitido.'); return false; } if (file.size > state.data.parameters.evidenceMaxSizeMb * 1024 * 1024) { Swal.showValidationMessage(`El archivo supera el máximo de ${state.data.parameters.evidenceMaxSizeMb} MB.`); return false; } return file; } });
  if (!result.isConfirmed) return;
  const file = result.value; const replacementId = `ev-${Date.now()}`;
  state.data.evidences.unshift({ id: replacementId, activityId: activity.id, fileName: file.name, type: file.type, size: Number((file.size / 1024 / 1024).toFixed(2)), uploadedAt: new Date().toISOString(), uploadedBy: state.currentUserId, status: 'Pendiente', reviewerId: null, reviewedAt: null, comment: '' });
  activity.evidenceId = replacementId; activity.status = 'Pendiente de validación';
  state.data.audit.unshift({ id: `aud-${Date.now()}`, action: 'Carga de nueva evidencia', entity: 'Evidencia', entityId: replacementId, userId: state.currentUserId, date: new Date().toISOString(), detail: `Reemplaza evidencia rechazada ${oldEvidence.id}` });
  renderApp(); Swal.fire({ title: 'Nueva evidencia adjuntada', text: 'Quedó pendiente de aprobación o rechazo.', icon: 'success', confirmButtonColor: '#079b92' });
}

async function addAdjustment() {
  const result = await Swal.fire({ title: 'Agregar ajuste', html: '<div class="text-start"><label class="form-label">Tipo<select id="adjustmentType" class="form-select"><option>Bonificación</option><option>Penalización</option></select></label><label class="form-label mt-2">Descripción<input id="adjustmentDescription" class="form-control" maxlength="120" placeholder="Ej: Felicitación por gestión destacada"></label></div>', showCancelButton: true, confirmButtonText: 'Agregar', cancelButtonText: 'Cancelar', confirmButtonColor: '#b92f1b', preConfirm: () => { const description = document.getElementById('adjustmentDescription').value.trim(); if (!description) { Swal.showValidationMessage('Ingresa una descripción.'); return false; } return { type: document.getElementById('adjustmentType').value, description }; } });
  if (!result.isConfirmed) return;
  const adjustment = { id: `adj-${Date.now()}`, ...result.value, percent: '', userId: state.currentUserId, periodId: state.currentPeriodId, status: 'Vigente' };
  state.data.adjustments = state.data.adjustments || []; state.data.adjustments.unshift(adjustment);
  state.data.audit.unshift({ id: `aud-${Date.now()}`, action: 'Registro de ajuste', entity: 'Ajuste', entityId: adjustment.id, userId: state.currentUserId, date: new Date().toISOString(), detail: `${adjustment.type}: ${adjustment.description}` });
  renderApp();
}

function updateAdjustment(adjustmentId, value) {
  const adjustment = (state.data.adjustments || []).find((candidate) => candidate.id === adjustmentId);
  if (!adjustment) return;
  adjustment.percent = value === '' ? '' : Number(value);
  state.data.audit.unshift({ id: `aud-${Date.now()}`, action: 'Actualización de ajuste', entity: 'Ajuste', entityId: adjustmentId, userId: state.currentUserId, date: new Date().toISOString(), detail: `Porcentaje actualizado a ${adjustment.percent}%` });
  Swal.fire({ title: 'Porcentaje guardado', text: 'El valor quedó disponible para el cálculo parametrizado.', icon: 'success', timer: 1600, showConfirmButton: false });
}

async function handleCommitmentUpdate(commitmentId) {
  const commitment = state.data.commitments.find((candidate) => candidate.id === commitmentId);
  const statuses = ['Ingresado', 'Pendiente', 'En proceso', 'Realizado'];
  const result = await Swal.fire({ title: 'Actualizar compromiso', input: 'select', inputOptions: Object.fromEntries(statuses.map((status) => [status, status])), inputValue: commitment.status, inputLabel: 'Nuevo estado', showCancelButton: true, confirmButtonText: 'Guardar cambio', cancelButtonText: 'Cancelar', confirmButtonColor: '#b92f1b' });
  if (!result.isConfirmed || result.value === commitment.status) return;
  const oldStatus = commitment.status; commitment.status = result.value; commitment.history.push({ from: oldStatus, to: result.value, date: '2026-09-22', author: state.currentUserId, comment: 'Actualización desde la agenda.' });
  state.data.audit.unshift({ id: `aud-${Date.now()}`, action: 'Cambio de estado', entity: 'Compromiso', entityId: commitment.id, userId: state.currentUserId, date: new Date().toISOString(), detail: `Estado cambió de ${oldStatus} a ${commitment.status}` });
  renderApp(); Swal.fire({ title: 'Estado actualizado', text: `El compromiso ahora está ${commitment.status.toLowerCase()}.`, icon: 'success', confirmButtonColor: '#b92f1b' });
}

function handleCommitmentSubmit(event) {
  event.preventDefault(); const form = event.target; if (!form.checkValidity()) { form.classList.add('was-validated'); return; }
  const id = `com-${String(state.data.commitments.length + 1).padStart(3, '0')}`;
  state.data.commitments.unshift({ id, description: byId('commitmentDescription').value.trim(), requester: byId('commitmentRequester').value.trim(), territory: byId('commitmentTerritory').value.trim(), responsibleId: state.currentUserId, supportArea: byId('commitmentSupport').value, dueDate: byId('commitmentDueDate').value, status: 'Ingresado', periodId: state.currentPeriodId, history: [] });
  state.data.audit.unshift({ id: `aud-${Date.now()}`, action: 'Registro de compromiso', entity: 'Compromiso', entityId: id, userId: state.currentUserId, date: new Date().toISOString(), detail: 'Compromiso creado en agenda colectiva' });
  bootstrap.Modal.getInstance(byId('commitmentModal')).hide(); renderApp(); Swal.fire({ title: 'Compromiso creado', text: 'El nuevo compromiso quedó disponible en la agenda colectiva.', icon: 'success', confirmButtonColor: '#b92f1b' });
}

function exportActivities() {
  const headers = ['Código', 'Fecha', 'Actividad', 'Responsable', 'Ítem', 'Estado'];
  const rows = state.data.activities.map((activity) => [activity.code, activity.date, activity.description, getUser(activity.userId).name, getItem(activity.itemId).name, activity.status]);
  const csv = [headers, ...rows].map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(';')).join('\n');
  const link = document.createElement('a'); link.href = URL.createObjectURL(new Blob([`\ufeff${csv}`], { type: 'text/csv;charset=utf-8' })); link.download = `sgr-actividades-${state.currentPeriodId}.csv`; link.click(); URL.revokeObjectURL(link.href);
  Swal.fire({ title: 'Exportación preparada', text: 'Se descargó el detalle de actividades con los datos del período.', icon: 'success', confirmButtonColor: '#b92f1b' });
}

async function openProfilePicker() {
  const options = Object.fromEntries(state.data.users.map((user) => [user.id, `${user.name} · ${user.roleLabel}`]));
  const result = await Swal.fire({ title: 'Perfil de demostración', input: 'select', inputOptions: options, inputValue: state.currentUserId, showCancelButton: true, confirmButtonText: 'Usar perfil', cancelButtonText: 'Cancelar', confirmButtonColor: '#b92f1b' });
  if (result.isConfirmed) { state.currentUserId = result.value; renderApp(); }
}
async function editParameters() { const parameters = state.data.parameters; const result = await Swal.fire({ title: 'Editar parámetros vigentes', html: `<div class="text-start"><label class="form-label">Tope de cumplimiento (%)<input id="maxCompliance" class="form-control" type="number" min="1" max="300" value="${parameters.maxCompliance}"></label><label class="form-label mt-2">Umbral colectivo (%)<input id="collectiveThreshold" class="form-control" type="number" min="0" max="100" value="${parameters.collectiveThreshold}"></label><label class="form-label mt-2">Inicio de semáforo ámbar (%)<input id="amberRatio" class="form-control" type="number" min="0" max="100" value="${parameters.amberRatio}"></label></div>`, showCancelButton: true, confirmButtonText: 'Guardar parámetros', cancelButtonText: 'Cancelar', confirmButtonColor: '#b92f1b', preConfirm: () => { const maxCompliance = Number(document.getElementById('maxCompliance').value); const collectiveThreshold = Number(document.getElementById('collectiveThreshold').value); const amberRatio = Number(document.getElementById('amberRatio').value); if (!maxCompliance || collectiveThreshold < 0 || collectiveThreshold > 100 || amberRatio < 0 || amberRatio > 100) { Swal.showValidationMessage('Ingresa valores válidos dentro de los rangos indicados.'); return false; } return { maxCompliance, collectiveThreshold, amberRatio }; } }); if (!result.isConfirmed) return; Object.assign(parameters, result.value); state.data.audit.unshift({ id: `aud-${Date.now()}`, action: 'Actualización de parámetros', entity: 'Parámetros', entityId: 'parameters', userId: state.currentUserId, date: new Date().toISOString(), detail: `Tope ${parameters.maxCompliance}%, umbral ${parameters.collectiveThreshold}%, ámbar ${parameters.amberRatio}%` }); renderApp(); Swal.fire({ title: 'Parámetros actualizados', text: 'Los indicadores del prototipo usan los nuevos valores.', icon: 'success', confirmButtonColor: '#079b92' }); }
function showPeriods() { state.currentView = 'periods'; renderApp(); }
function showAuditInfo() { Swal.fire({ title: 'Auditoría del prototipo', text: 'Esta vista demuestra la trazabilidad funcional. En producción, el registro debe persistir en backend y protegerse contra alteraciones no autorizadas.', icon: 'info', confirmButtonColor: '#b92f1b' }); }

async function init() {
  try {
    const response = await fetch(new URL('../data/sgr.json', import.meta.url)); if (!response.ok) throw new Error('No se pudo cargar el JSON'); state.data = await response.json();
    const requestedRole = document.body.dataset.sgrRole;
    state.currentUserId = state.data.users.find((user) => user.role === requestedRole)?.id || state.data.currentUserId;
    if (requestedRole === 'Admin') state.currentView = 'admin';
    const select = byId('periodSelect'); select.innerHTML = state.data.periods.map((period) => `<option value="${period.id}">${escapeHtml(period.name)}</option>`).join(''); select.value = state.currentPeriodId; select.addEventListener('change', (event) => { state.currentPeriodId = event.target.value; renderApp(); });
    document.querySelectorAll('.nav-link').forEach((button) => button.addEventListener('click', () => { state.currentView = button.dataset.view; byId('sidebar').classList.remove('open'); renderApp(); }));
    byId('menuButton').addEventListener('click', () => byId('sidebar').classList.toggle('open')); byId('profileButton').addEventListener('click', openProfilePicker); byId('notificationButton').addEventListener('click', () => { state.currentView = 'agenda'; renderApp(); });
    renderApp();
  } catch (error) { byId('appContent').innerHTML = renderEmpty('bi-database-exclamation', 'No se pudo cargar la información', 'Ejecuta el proyecto mediante un servidor local para cargar data/sgr.json.'); console.error(error); }
}

init();
