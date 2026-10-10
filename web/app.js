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
async function refresh(){try{const data=await api('state');loggedIn=true;$('login').textContent='Sair';products=data.products;$('status').textContent=data.session?'● Caixa aberto #'+data.session.id+' • Saldo em dinheiro: '+money(data.session.balance):'● Caixa fechado';render();renderRegistered()}catch(e){loggedIn=false;$('login').textContent='Entrar';$('status').textContent=e.message}}
function render(){const q=$('search').value.toLowerCase();$('products').replaceChildren();for(const p of products.filter(p=>p.name.toLowerCase().includes(q))){const b=document.createElement('button');b.className='product';const n=document.createElement('span');n.textContent=p.name;const v=document.createElement('strong');v.textContent=money(p.price);const info=document.createElement('div');info.className='pinfo';info.append(n,v);showImage(p,b);b.append(info);b.onclick=()=>{cart[p.id]=(cart[p.id]||0)+1;render()};$('products').append(b)}$('cart').replaceChildren();let total=0;for(const [id,qty] of Object.entries(cart)){const p=products.find(p=>p.id==id);if(!p)continue;total+=p.price*qty;const row=document.createElement('div');row.className='item';const name=document.createElement('span');name.textContent=p.name+' • '+money(p.price*qty);const minus=document.createElement('button');minus.textContent='−';minus.onclick=()=>{if(--cart[id]<=0)delete cart[id];render()};const count=document.createElement('b');count.textContent=qty;const plus=document.createElement('button');plus.textContent='+';plus.onclick=()=>{cart[id]++;render()};row.append(name,minus,count,plus);$('cart').append(row)}$('total').textContent=money(total)}
async function act(path,body){try{await api(path,'POST',body);await refresh()}catch(e){alert(e.message)}}
$('login').onclick=async()=>{
 if(loggedIn){try{await api('logout','POST');loggedIn=false;products=[];cart={};$('login').textContent='Entrar';render();renderRegistered();$('status').textContent='Sessão encerrada.'}catch(e){alert(e.message)}return}
 const password=prompt('Digite sua senha do PDV:');if(password===null)return;
 try{await api('login','POST',{password});await refresh()}catch(e){alert(e.message)}
};
$('search').oninput=render;$('clear').onclick=()=>{cart={};render()};
document.querySelectorAll('[data-pay]').forEach(b=>b.onclick=()=>{payment=b.dataset.pay;document.querySelectorAll('[data-pay]').forEach(x=>x.classList.toggle('chosen',x===b))});
$('finish').onclick=async()=>{if(!Object.keys(cart).length)return alert('Adicione produtos.');if(!confirm('Confirmar venda de '+$('total').textContent+' por '+payment+'?'))return;try{const s=await api('sales','POST',{cart,payment});cart={};await refresh();alert('Venda #'+s.id+' registrada!')}catch(e){alert(e.message)}};
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
document.querySelectorAll('[data-tab]').forEach(b=>b.onclick=async()=>{document.querySelectorAll('[data-tab]').forEach(x=>x.classList.toggle('selected',x===b));document.querySelectorAll('.page').forEach(x=>x.classList.toggle('active',x.id===b.dataset.tab));if(b.dataset.tab==='vendas'){try{const rows=await api('history');$('history').replaceChildren();rows.forEach(r=>{const d=document.createElement('div');d.textContent='#'+r.id+' • '+r.created+' • '+r.payment+' • '+money(r.total);$('history').append(d)})}catch(e){alert(e.message)}}});refresh();
