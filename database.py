
def register_user(db,chat_id,email):
    doc_ref = db.collection("users").document(chat_id)
    doc_ref.set({
	    "token_kmu": chat_id,
		"email": email
	})

def save_info_to_db(db,chat_id,info):
    doc_ref = db.collection("info").document(chat_id)
    doc_ref.set({
	    "token_kmu": chat_id,
		"info": info
	})
    
def save_kmu_summary_to_db(db,chat_id,sum_prompt):
    doc_ref = db.collection("kmu_summaries").document(chat_id)
    doc_ref.set({
	    "token_kmu": chat_id,
		"summary": sum_prompt
	})

def save_chat_to_db(db,chat_id,chat):
    doc_ref = db.collection("chats").document(chat_id)
    doc_ref.set({
	    "token_kmu": chat_id,
		"chat": chat
	})

def save_interview_to_db(db,chat_id,client_id,interview):
    doc_ref = db.collection("interviews").document(client_id)
    doc_ref.set({
	    "token_kmu": chat_id,
        "token_customer": client_id,
		"interview": interview
	})
    

def load_summary_from_db(db,chat_id):
    doc_ref = db.collection("kmu_summaries").document(chat_id)
    doc = doc_ref.get().to_dict()
    return doc["summary"]

    
def load_info_from_db(db,chat_id):
    doc_ref = db.collection("info").document(chat_id)
    doc = doc_ref.get().to_dict()
    return doc["info"]   
    
 
def load_email_from_db(db,chat_id):
    doc_ref = db.collection("users").document(chat_id)
    doc = doc_ref.get().to_dict()
    return doc["email"]