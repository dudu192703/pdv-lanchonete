let loggedIn=false,products=[],cart={},payment='Dinheiro';
const $=id=>document.getElementById(id),money=n=>(n/100).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
async function api(path,method='GET',body){const r=await fetch('/api/'+path,{method,credentials:'same-origin',headers:{'X-PDV-Request':'1','Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});const j=await r.json();if(!r.ok)throw Error(j.detail||'Erro na operação');return j}
const imageUrls=new Map();
async function loadImage(id){
  try{
    const r=await fetch('/api/products/'+id+'/image',{credentials:'same-origin'});
    if(!r.ok)return;
    const url=URL.createObjectURL(await r.blob());
    if(imageUrls.has(id))URL.revokeObjectURL(imageUrls.get(id));
    imageUrls.set(id,url);
    document.querySelectorAll('img[data-product="'+id+'"]').forEach(img=>img.src=url);
  }catch(e){console.warn('Imagem indisponível',e)}
}
function showImage(p,parent){
  if(p.image){
    const img=document.createElement('img');img.alt=p.name;img.dataset.product=p.id;
    if(imageUrls.has(p.id))img.src=imageUrls.get(p.id);else loadImage(p.id);
    parent.append(img);
  }else{
    const placeholder=document.createElement('div');placeholder.className='placeholder';placeholder.textContent='🍔';parent.append(placeholder);
  }
}
function renderInventory(items=products){
 const root=$('inventory');root.replaceChildren();
 for(const p of items){
   const row=document.createElement('div');row.className='stock-row';
   const label=document.createElement('span');label.textContent=p.name;
   const current=document.createElement('strong');current.textContent=p.stock+' un.';
   if(p.stock===0)current.className='out-of-stock';
   const input=document.createElement('input');input.type='number';input.min='0';input.step='1';input.value=p.stock;input.setAttribute('aria-label','Quantidade de '+p.name);
   const save=document.createElement('button');save.textContent='Salvar';
   save.onclick=async()=>{
     const quantity=Number(input.value);
     if(!Number.isSafeInteger(quantity)||quantity<0){alert('Informe uma quantidade inteira válida.');return}
     save.disabled=true;
     try{await api('products/'+p.id+'/stock','PUT',{quantity});await refresh()}
     catch(e){alert(e.message);save.disabled=false}
   };
   row.append(label,current,input,save);root.append(row);
 }
}
async function refreshInventory(){
 try{
   const items=await api('inventory');
   renderInventory(items);
   $('inventoryError').textContent=items.length?'':'Nenhum produto cadastrado.';
 }catch(e){$('inventoryError').textContent='Erro ao carregar estoque: '+e.message}
}
function renderRegistered(){
  const el=$('registered');el.replaceChildren();
  for(const p of products){
    const row=document.createElement('div');row.className='registered-item';
    if(p.image){const img=document.createElement('img');img.dataset.product=p.id;img.alt=p.name;if(imageUrls.has(p.id))img.src=imageUrls.get(p.id);row.append(img)}
    const name=document.createElement('span');name.textContent=p.name+' — '+money(p.price);
    const change=document.createElement('button');change.textContent='📷 Alterar foto';
    change.onclick=()=>{const input=document.createElement('input');input.type='file';input.accept='image/jpeg,image/png,image/webp';input.onchange=async()=>{if(input.files[0])await sendImage(p.id,input.files[0])};input.click()};
    row.append(name,change);el.append(row);
  }
}
async function sendImage(id,file){
  if(file.size>4_000_000)throw Error('A foto deve ter no máximo 4 MB.');
  const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onerror=()=>reject(Error('Não foi possível ler a imagem.'));reader.onload=()=>resolve(reader.result.split(',')[1]);reader.readAsDataURL(file)});
  await api('products/'+id+'/image','PUT',{data});
  if(imageUrls.has(id)){URL.revokeObjectURL(imageUrls.get(id));imageUrls.delete(id)}
  await refresh();
}
async function refresh(){try{const data=await api('state');loggedIn=true;$('login').textContent='Sair';products=data.products;$('status').textContent=data.session?'● Caixa aberto #'+data.session.id+' • Saldo em dinheiro: '+money(data.session.balance):'● Caixa fechado';render();renderRegistered();await refreshInventory()}catch(e){loggedIn=false;$('login').textContent='Entrar';$('status').textContent=e.message}}
function render(){const q=$('search').value.toLowerCase();$('products').replaceChildren();for(const p of products.filter(p=>p.name.toLowerCase().includes(q))){const b=document.createElement('button');b.className='product';if(p.stock===0)b.classList.add('sold-out');const n=document.createElement('span');n.textContent=p.name;const v=document.createElement('strong');v.textContent=money(p.price);const stock=document.createElement('small');stock.textContent=p.stock>0?'Estoque: '+p.stock:'Sem estoque';const info=document.createElement('div');info.className='pinfo';info.append(n,v,stock);showImage(p,b);b.append(info);b.onclick=()=>{if((cart[p.id]||0)>=p.stock){alert('Estoque insuficiente para '+p.name+'. Disponível: '+p.stock);return}cart[p.id]=(cart[p.id]||0)+1;render()};$('products').append(b)}$('cart').replaceChildren();let total=0;for(const [id,qty] of Object.entries(cart)){const p=products.find(p=>p.id==id);if(!p)continue;total+=p.price*qty;const row=document.createElement('div');row.className='item';const name=document.createElement('span');name.textContent=p.name+' • '+money(p.price*qty);const minus=document.createElement('button');minus.textContent='−';minus.onclick=()=>{if(--cart[id]<=0)delete cart[id];render()};const count=document.createElement('b');count.textContent=qty;const plus=document.createElement('button');plus.textContent='+';plus.onclick=()=>{if(cart[id]>=p.stock){alert('Estoque insuficiente para '+p.name);return}cart[id]++;render()};row.append(name,minus,count,plus);$('cart').append(row)}$('total').textContent=money(total)}
async function act(path,body){try{await api(path,'POST',body);await refresh()}catch(e){alert(e.message)}}
$('login').onclick=async()=>{
 if(loggedIn){try{await api('logout','POST');loggedIn=false;products=[];cart={};$('login').textContent='Entrar';render();renderRegistered();renderInventory();$('status').textContent='Sessão encerrada.'}catch(e){alert(e.message)}return}
 const password=prompt('Digite sua senha do PDV:');if(password===null)return;
 try{await api('login','POST',{password});await refresh()}catch(e){alert(e.message)}
};
$('search').oninput=render;$('clear').onclick=()=>{cart={};render()};
document.querySelectorAll('[data-pay]').forEach(b=>b.onclick=()=>{payment=b.dataset.pay;document.querySelectorAll('[data-pay]').forEach(x=>x.classList.toggle('chosen',x===b))});
$('finish').onclick=async()=>{if(!Object.keys(cart).length)return alert('Adicione produtos.');const btn=$('finish');if(btn.disabled)return;btn.disabled=true;try{const s=await api('sales','POST',{cart,payment});cart={};await refresh();$('status').textContent='✓ Venda #'+s.id+' registrada com sucesso!'}catch(e){alert(e.message)}finally{btn.disabled=false}};
$('productForm').onsubmit=async e=>{
 e.preventDefault();const form=e.target;const f=new FormData(form);const button=form.querySelector('button');button.disabled=true;
 try{
   const before=new Set(products.map(p=>p.id));
   await api('products','POST',{name:f.get('name'),price:f.get('price')});
   await refresh();
   const created=products.find(p=>!before.has(p.id));
   const file=f.get('image');
   if(created&&file&&file.size)await sendImage(created.id,file);
   form.reset();alert('Produto cadastrado!');
 }catch(err){alert('Não foi possível concluir: '+err.message)}
 finally{button.disabled=false}
};
function askAmount(title){return prompt(title+' — valor em reais (ex.: 10,50):')}
$('open').onclick=()=>{const amount=askAmount('Abertura');if(amount!==null)act('open',{amount})};
$('close').onclick=()=>{const amount=askAmount('Dinheiro contado no fechamento');if(amount!==null&&confirm('Confirmar fechamento?'))act('close',{amount})};
async function movement(kind){const amount=askAmount(kind);if(amount===null)return;const note=prompt('Motivo:');if(note!==null)await act('movement',{kind,amount,note})}
$('withdraw').onclick=()=>movement('Sangria');$('supply').onclick=()=>movement('Suprimento');
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=async()=>{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('selected',x===b));document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.id===b.dataset.tab));if(b.dataset.tab==='estoque')await refreshInventory();if(b.dataset.tab==='vendas')await loadSales();if(b.dataset.tab==='comandas')await loadTabs()});refresh();

async function loadSales(){
 try{
  const rows=await api('history');
  const select=$('salesProduct'),chosen=select.value;
  select.replaceChildren(new Option('Todos os produtos',''));
  for(const p of products)select.add(new Option(p.name,p.id));
  select.value=chosen;
  const root=$('history');root.replaceChildren();
  for(const sale of rows){
   const detail=document.createElement('details');detail.className='sale-detail';
   const head=document.createElement('summary');
   head.textContent='#'+sale.id+' • '+sale.created+' • '+sale.payment+' • '+money(sale.total);
   const content=document.createElement('div');content.className='sale-lines';
   detail.append(head,content);
   detail.addEventListener('toggle',async()=>{
    if(!detail.open||detail.dataset.loaded)return;
    content.textContent='Carregando...';
    try{
     const items=await api('sales/'+sale.id+'/items');
     content.replaceChildren();
     for(const item of items){
      const line=document.createElement('div');
      line.textContent=item.quantity+'× '+item.name+' — '+money(item.quantity*item.price);
      content.append(line);
     }
     if(!items.length)content.textContent='Nenhum item encontrado.';
     detail.dataset.loaded='1';
    }catch(e){content.textContent='Erro: '+e.message}
   });
   root.append(detail);
  }
 }catch(e){$('history').textContent='Erro ao carregar vendas: '+e.message}
}
$('salesSearch').onclick=async()=>{
 const id=$('salesProduct').value;
 const root=$('salesSummary');root.textContent='Buscando...';
 try{
  const rows=await api('sales-summary'+(id?'?product_id='+encodeURIComponent(id):''));
  root.replaceChildren();
  let qty=0,total=0;
  for(const p of rows){
   qty+=p.quantity;total+=p.total;
   const row=document.createElement('div');row.className='summary-line';
   row.textContent=p.name+' — '+p.quantity+' unidade(s) • '+money(p.total);
   root.append(row);
  }
  const foot=document.createElement('strong');
  foot.textContent='Total: '+qty+' unidade(s) • '+money(total);
  root.append(foot);
 }catch(e){root.textContent='Erro: '+e.message}
};

let activeTab=null;
async function loadTabs(){
 try{
  const tabs=await api('tabs'),root=$('tabList');root.replaceChildren();
  for(const tab of tabs){
   const row=document.createElement('div');row.className='tab-row';
   const open=document.createElement('button');open.textContent=tab.customer+' • '+money(tab.total);
   open.onclick=()=>showTab(tab.id,tab.customer);
   const close=document.createElement('button');close.textContent='Fechar conta';close.onclick=()=>closeTab(tab.id,tab.customer);
   row.append(open,close);root.append(row);
  }
  if(!tabs.some(t=>t.id===activeTab)){$('tabDetail').replaceChildren();activeTab=null}
 }catch(e){$('tabList').textContent=e.message}
}
$('tabForm').onsubmit=async e=>{
 e.preventDefault();const name=$('customerName').value.trim();if(!name)return;
 try{const tab=await api('tabs','POST',{customer:name});$('customerName').value='';await loadTabs();await showTab(tab.id,name)}catch(err){alert(err.message)}
};
async function showTab(id,customer){
 activeTab=id;const root=$('tabDetail');root.replaceChildren();
 const heading=document.createElement('h3');heading.textContent='Comanda de '+customer;
 const lines=document.createElement('div');lines.className='tab-lines';
 const productsBox=document.createElement('div');productsBox.className='tab-products';
 root.append(heading,lines,productsBox);
 async function reload(){
  const items=await api('tabs/'+id);
  lines.replaceChildren();
  let total=0;
  for(const item of items){
   const row=document.createElement('div');row.textContent=item.quantity+'× '+item.name+' — '+money(item.price*item.quantity);
   total+=item.price*item.quantity;lines.append(row);
  }
  const summary=document.createElement('strong');summary.textContent='Total: '+money(total);lines.append(summary);
 }
 try{await reload()}catch(e){lines.textContent=e.message}
 for(const p of products){
  const b=document.createElement('button');b.textContent=p.name+' • '+money(p.price);
  b.onclick=async()=>{b.disabled=true;try{await api('tabs/'+id+'/items','POST',{product_id:p.id});await reload();await loadTabs()}catch(e){alert(e.message)}finally{b.disabled=false}};
  productsBox.append(b);
 }
}
async function closeTab(id,customer){
 try{
  const items=await api('tabs/'+id);
  if(!items.length)return alert('Comanda sem produtos.');
  const total=items.reduce((n,i)=>n+i.price*i.quantity,0);
  const details=items.map(i=>i.quantity+'× '+i.name+' — '+money(i.price*i.quantity)).join('\n');
  if(!confirm('Fechar conta de '+customer+'?\n\n'+details+'\n\nTotal: '+money(total)))return;
  const payment=prompt('Pagamento: Dinheiro, Pix ou Cartão','Dinheiro');
  if(payment===null)return;
  const method=['Dinheiro','Pix','Cartão'].find(x=>x.toLowerCase()===payment.trim().toLowerCase());
  if(!method)return alert('Escolha Dinheiro, Pix ou Cartão.');
  const result=await api('tabs/'+id+'/close','POST',{payment:method});
  await refresh();await loadTabs();alert('Comanda fechada. Venda #'+result.id+' • '+money(result.total));
 }catch(e){alert(e.message)}
}
