const form=document.getElementById('reviewLogin');
const input=document.getElementById('invitation');
const button=document.getElementById('signIn');
const message=document.getElementById('message');
form.addEventListener('submit',async event=>{
  event.preventDefault();button.disabled=true;message.textContent='';
  const code=input.value.trim();input.value='';
  try{
    const response=await fetch('/api/reviewer/session',{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})
    });
    if(response.ok){location.replace('/');return}
    message.textContent=response.status===429?'Too many attempts. Please wait a minute.':'Invalid or expired invitation code.';
  }catch(error){message.textContent='Connection failed. Please try again.'}
  button.disabled=false;input.focus();
});
