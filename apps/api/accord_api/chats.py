"""One person-facing inbox; each underlying work item keeps its original ACL."""
from fastapi import APIRouter, Depends, HTTPException
from . import access, store
from .auth import principal
from .commands import Operation, operate

router=APIRouter(prefix='/api/chats')


class OpenChat(Operation):
    target_id:str
    new_item:bool=False


def pair_threads(db,uid,peer):
    result=[]
    for row in db.execute("SELECT id FROM accord_threads WHERE kind='peer' AND ((owner_id=? AND target_id=?) OR (owner_id=? AND target_id=?)) ORDER BY created_at,rowid",(uid,peer,peer,uid)).fetchall():
        try:result.append(access.thread_for(uid,row['id'],db))
        except HTTPException:pass
    return result


@router.post('/open')
def open_chat(body:OpenChat,uid=Depends(principal)):
    def run(db):
        if uid==body.target_id or not db.execute('SELECT 1 FROM accord_accounts WHERE unit_id=?',(body.target_id,)).fetchone():
            raise HTTPException(404,'请选择一位同事。')
        existing=pair_threads(db,uid,body.target_id)
        if not body.new_item and existing:return {'id':max(existing,key=lambda t:(t['updated_at'],t['id']))['id']}
        # Repeated clicks cannot create several empty or concurrently running requests.
        own=[t for t in existing if t['owner_id']==uid and t['status']=='agent' and t['purpose']=='ordinary']
        if own:return {'id':max(own,key=lambda t:t['updated_at'])['id']}
        tid,now=store.new_id('thread'),store.now()
        db.execute('INSERT INTO accord_threads(id,owner_id,target_id,title,kind,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',(tid,uid,body.target_id,'新的协作','peer',now,now))
        return {'id':tid}
    return operate(uid,body,'chat:open',run)
