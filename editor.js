(() => {
  const type = document.querySelector('#page-type');
  const box = document.querySelector('#config-editor');
  const raw = document.querySelector('#config-json');
  const title = document.querySelector('#config-title');
  const help = document.querySelector('#config-help');
  let config = {};
  try { config = JSON.parse(raw.value || '{}'); } catch { config = {}; }
  const esc = (v = '') => String(v).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  const sync = () => { raw.value = JSON.stringify(config); };
  const input = (label, key, value) => `<label>${label}<input data-key="${key}" value="${esc(value || '')}"></label>`;
  const render = () => {
    const kind = type.value;
    if (kind === 'informativa') { title.textContent='Sin campos adicionales'; help.textContent='Esta página muestra título, texto e imagen. Puede publicarse tal cual.'; box.innerHTML=''; config={}; sync(); return; }
    if (kind === 'confirmacion') {
      title.textContent='Botones de confirmación'; help.textContent='Los dos botones se guardarán como respuesta y mostrarán el mismo mensaje posterior.';
      config = {...{boton_1:'Sí, ahí estaré', boton_2:'No puedo esta vez', mensaje_posterior:'Gracias por responder. El comité lo registró correctamente.'}, ...config};
      box.innerHTML=input('Primer botón','boton_1',config.boton_1)+input('Segundo botón','boton_2',config.boton_2)+`<label>Mensaje posterior<textarea data-key="mensaje_posterior" rows="3">${esc(config.mensaje_posterior)}</textarea></label>`;
    } else if (kind === 'especial') {
      title.textContent='Momento especial'; help.textContent='Diseño cálido, un botón y un mensaje posterior. La interacción queda registrada en el archivo.';
      config = {...{boton_principal:'Abrir con calma', mensaje_posterior:'Gracias por recibir este pequeño detalle.'}, ...config};
      box.innerHTML=input('Texto del botón','boton_principal',config.boton_principal)+`<label>Mensaje posterior<textarea data-key="mensaje_posterior" rows="3">${esc(config.mensaje_posterior)}</textarea></label>`;
    } else {
      title.textContent='Preguntas de encuesta'; help.textContent='Agrega, edita o elimina preguntas. Opción múltiple separa sus opciones por coma.';
      config.preguntas = Array.isArray(config.preguntas) && config.preguntas.length ? config.preguntas : [{texto:'¿Cómo estuvo el trámite?',tipo:'escala',min:1,max:5,requerida:true}];
      box.innerHTML=`<div id="questions">${config.preguntas.map(questionHtml).join('')}</div><button type="button" class="button ghost small" id="add-question">+ Agregar pregunta</button><label>Mensaje posterior<textarea data-key="mensaje_posterior" rows="3">${esc(config.mensaje_posterior || 'Gracias por completar el formulario.')}</textarea></label>`;
    }
    sync();
  };
  const questionHtml = (q, index) => `<article class="question" data-index="${index}"><button type="button" class="remove-question" title="Eliminar">×</button><label>Pregunta<input data-question="texto" value="${esc(q.texto || '')}"></label><div class="form-grid"><label>Tipo<select data-question="tipo"><option value="opcion" ${q.tipo==='opcion'?'selected':''}>Opción múltiple</option><option value="escala" ${q.tipo==='escala'?'selected':''}>Escala numérica</option><option value="texto" ${q.tipo==='texto'?'selected':''}>Texto libre</option></select></label><label class="check-label"><input data-question="requerida" type="checkbox" ${q.requerida !== false?'checked':''}> Obligatoria</label></div><div class="question-extra">${q.tipo==='opcion'?`<label>Opciones (separadas por coma)<input data-question="opciones" value="${esc((q.opciones||[]).join(', '))}"></label>`:q.tipo==='escala'?`<div class="form-grid">${input('Mínimo','min',q.min||1).replace('data-key','data-question')}${input('Máximo','max',q.max||5).replace('data-key','data-question')}</div>`:''}</div></article>`;
  type.addEventListener('change', () => { config={}; render(); });
  box.addEventListener('input', (event) => {
    const target=event.target, article=target.closest('.question');
    if (target.dataset.key) { config[target.dataset.key]=target.value; sync(); }
    if (article && target.dataset.question) { const q=config.preguntas[Number(article.dataset.index)]; const key=target.dataset.question; q[key]=key==='opciones'?target.value.split(',').map(x=>x.trim()).filter(Boolean):target.value; if(key==='min'||key==='max')q[key]=Number(q[key]); sync(); }
  });
  box.addEventListener('change', (event) => {
    const target=event.target, article=target.closest('.question');
    if (article && target.dataset.question) { const q=config.preguntas[Number(article.dataset.index)]; q[target.dataset.question]=target.type==='checkbox'?target.checked:target.value; if(target.dataset.question==='tipo') render(); sync(); }
  });
  box.addEventListener('click', (event) => {
    if(event.target.id==='add-question'){config.preguntas.push({texto:'',tipo:'texto',requerida:true});render();}
    if(event.target.classList.contains('remove-question')){config.preguntas.splice(Number(event.target.closest('.question').dataset.index),1);render();}
  });
  render();
})();
