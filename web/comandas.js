const $=id=>document.getElementById(id);
const money=n=>(n/100).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
let products=[],tabs=[],active=null,items=[],busy=false;
async function api(path,method='GET',body){
 const r=await fetch('/api/'+path,{method,credentials:'same-origin',headers:{'X-PDV-Request':'1','Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
 const j=await r.json().catch(()=>({}));if(!r.ok)throw Error(j.detail||'Erro '+r.status);return j;
}
function message(s){$('message').textContent=s}
function pendingCount(){return items.reduce((n,i)=>n+Math.max(0,i.quantity-i.sent_quantity),0)}
function switchWarning(){return active!==null&&pendingCount()>0&&!confirm('Atenção! Existem '+pendingCount()+' pedido(s) pendente(s) de envio à cozinha nesta comanda. Deseja trocar mesmo assim?')}
async function initialize(){
 try{products=await api('waiter/products');$('loginPanel').hidden=true;$('workspace').hidden=false;await loadTabs();message('')}
 catch(e){$('loginPanel').hidden=false;$('workspace').hidden=true;message(e.message)}
}
$('loginForm').onsubmit=async e=>{e.preventDefault();try{await api('waiter/login','POST',{password:$('password').value});$('password').value='';await initialize()}catch(err){message(err.message)}};
$('logout').onclick=async()=>{if(switchWarning())return;try{await api('waiter/logout','POST',{})}catch(e){}active=null;items=[];$('workspace').hidden=true;$('loginPanel').hidden=false};
async function loadTabs(){
 tabs=await api('tabs');const root=$('tabs');root.replaceChildren();
 for(const tab of tabs){
  const row=document.createElement('div');row.className='tab'+(tab.id===active?' active':'');
  const btn=document.createElement('button');btn.textContent=tab.customer+' • '+money(tab.total);
  btn.onclick=()=>selectTab(tab.id);
  row.append(btn);root.append(row);
 }
 if(active!==null&&!tabs.some(t=>t.id===active)){active=null;items=[];$('detail').hidden=true}
}
async function selectTab(id){
 if(busy||id===active)return;
 if(switchWarning())return;
 active=id;items=[];await renderTab();await loadTabs();
}
async function renderTab(){
 if(active===null)return;
 const id=active,tab=tabs.find(t=>t.id===id);
 $('detail').hidden=false;$('heading').textContent='Comanda de '+(tab?.customer||'#'+id);
 try{items=await api('tabs/'+id)}catch(e){message(e.message);return}
 if(active!==id)return;
 const sent=$('sent'),pending=$('pending');sent.replaceChildren();pending.replaceChildren();
 let total=0;
 for(const item of items){
  total+=item.price*item.quantity;
  if(item.sent_quantity){const line=document.createElement('div');line.className='line';line.textContent=item.sent_quantity+'× '+item.name+(item.choices?' ('+item.choices+')':'')+' — '+money(item.sent_quantity*item.price);sent.append(line)}
  const qty=item.quantity-item.sent_quantity;
  if(qty>0){
   const line=document.createElement('div');line.className='line';
   const label=document.createElement('span');label.textContent=qty+'× '+item.name+(item.choices?' ('+item.choices+')':'')+' — '+money(qty*item.price);
   const remove=document.createElement('button');remove.textContent='Retirar 1';remove.onclick=async()=>{
    remove.disabled=true;try{await api(item.variant_id?'tabs/'+id+'/variant-items/'+item.variant_id:'tabs/'+id+'/items/'+item.product_id,'DELETE');await renderTab();await loadTabs()}catch(e){message(e.message);remove.disabled=false}
   };line.append(label,remove);pending.append(line);
  }
 }
 if(!sent.children.length)sent.textContent='Nenhum pedido enviado.';
 if(!pending.children.length)pending.textContent='Nenhum pedido pendente.';
 $('total').textContent='Total da comanda: '+money(total);
 $('send').disabled=!pendingCount();
 renderProducts();
}
function renderProducts(){
 const root=$('products');root.replaceChildren();const query=$('search').value.toLocaleLowerCase('pt-BR');
 for(const p of products.filter(p=>p.name.toLocaleLowerCase('pt-BR').includes(query))){
  const b=document.createElement('button');b.className='product';b.disabled=p.stock===0;
  if(p.image){const img=document.createElement('img');img.alt=p.name;img.loading='lazy';img.src='/api/products/'+p.id+'/image';b.append(img)}
  const name=document.createElement('strong');name.textContent=p.name;
  const price=document.createElement('span');price.textContent=money(p.price)+(p.stock===0?' • Sem estoque':'');b.append(name,price);
  b.onclick=async()=>{const id=active;b.disabled=true;try{const choices=await chooseVariants(p.id);if(choices===null)return;await api('tabs/'+id+'/items','POST',{product_id:p.id,choices});await renderTab();await loadTabs()}catch(e){message(e.message)}finally{b.disabled=false}};
  root.append(b);
 }
}
$('search').oninput=renderProducts;
$('newForm').onsubmit=async e=>{
 e.preventDefault();if(switchWarning())return;
 const customer=$('customer').value.trim();if(!customer)return;
 try{const result=await api('tabs','POST',{customer});$('customer').value='';active=null;items=[];await loadTabs();await selectTab(result.id)}catch(err){message(err.message)}
};
$('send').onclick=async()=>{
 if(active===null||!pendingCount())return;
 const id=active;$('send').disabled=true;busy=true;
 try{const result=await api('tabs/'+id+'/kitchen','POST',{});message(result.items+' unidade(s) enviada(s) para a cozinha.');await renderTab();await loadTabs()}
 catch(e){message('Falha no envio: '+e.message)}finally{busy=false;$('send').disabled=!pendingCount()}
};
window.addEventListener('beforeunload',e=>{if(pendingCount()>0){e.preventDefault();e.returnValue=''}});
initialize();
async function chooseVariants(productId){
 const groups=await api('products/'+productId+'/variants');
 const choices={};
 for(const g of groups){
  if(!g.options.length)throw Error('A variedade "'+g.name+'" não possui opções cadastradas.');
  const text=g.options.map((o,i)=>(i+1)+' - '+o.name).join('\\n');
  const answer=prompt(g.name+'\\n'+text+'\\nDigite o número da opção:');
  if(answer===null)return null;
  const index=Number(answer);
  if(!Number.isInteger(index)||index<1||index>g.options.length)throw Error('Escolha inválida para '+g.name+'.');
  choices[String(g.id)]=g.options[index-1].id;
 }
 return choices;
}
