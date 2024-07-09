#app2.py
from langchain_openai import ChatOpenAI
from langchain_openai import OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain.chains import create_history_aware_retriever
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_pinecone import PineconeVectorStore
from langsmith import Client
from langchain_community.chat_message_histories import StreamlitChatMessageHistory
from google.cloud import firestore
from google.oauth2 import service_account
from database import load_summary_from_db, load_info_from_db, save_interview_to_db, load_email_from_db
import streamlit as st
import uuid
import os
import time
import json

PINECONE_API_KEY=os.environ['PINECONE_API_KEY']
LANGCHAIN_TRACING_V2=os.environ['LANGCHAIN_TRACING_V2']
LANGCHAIN_ENDPOINT=os.environ['LANGCHAIN_ENDPOINT']
LANGCHAIN_API_KEY=os.environ['LANGCHAIN_API_KEY']
LANGCHAIN_PROJECT=os.environ['LANGCHAIN_PROJECT']
OPENAI_API_KEY=os.environ['OPENAI_API_KEY']

key_dict = json.loads(st.secrets["textkey"])
creds = service_account.Credentials.from_service_account_info(key_dict)
db = firestore.Client(credentials=creds, project="llm-projekt")

index_name="llm"
client = Client()

#chat_id -> id of kmu
if "chat_id" not in st.session_state:
    st.session_state.chat_id=""

if "product_info" not in st.session_state:
    st.session_state.product_info=""

if "det_product_info" not in st.session_state:
    st.session_state.det_product_info=""

if "answers" not in st.session_state:
    st.session_state.answers=[]

if "sum_prompt" not in st.session_state:
    st.session_state.sum_prompt=""


st.title("FragenFabrik")

if 'page' not in st.session_state:
    st.session_state.page = "page1"

def load_retriever():
    index_name = "llm"
    embedding=OpenAIEmbeddings()
    vectorstore = PineconeVectorStore(index_name=index_name, embedding=embedding)
    retriever=vectorstore.as_retriever(
    search_kwargs={"namespace":"llm2"}
    )

    return retriever

def create_prompt_template(det_product_info,product_info):
    
    #product_info=load_summary_from_db(c, st.session_state.chat_id)

    prompt_template="""As a helpful AI interview bot, your task is to conduct a user interview with a potential user about a product that does not yet exist. 
You are a professional for user-centred development and user expirience interviews. Your goal is to generate new knowledge about users, their experiences, needs and weaknesses. 
As a context for your interview, you have a summary of an interview that was conducted with the product owner. Here you will find all the relevant information about the product that you should use to create the questions:\n"""+product_info+"\n"+ """Use your common knowledge and also use the following questions from a questionnaire and place suitable questions in the right context to obtain precise information: 
{context}.\n
"""+ "Here is some essential information about the interview and the product that you should definitely use:\n"+det_product_info+"\n"+"""
If a question is answered very briefly and incompletely, ask a follow-up question. Your questions should not be asked all at once but alternate with the user's answers.
For answers that have nothing to do with the question asked, reply in an appropriate way to the context and try to re-enter the interview with a new question.
Make sure that you do not ask any questions twice.
Once all the questions have been asked, ask the product owner if they would like to add any further information and respond to their answer.
At the end also point out that the interview can be concluded by entering "exit" and a summary of the interview will then be shown."""

    return prompt_template

def split_response(response):
     for word in response.split():
        yield word + " "
        time.sleep(0.06)


def interview():
    #email= load_email_from_db(c,st.session_state.chat_id)
    retriever = load_retriever()
    msgs = StreamlitChatMessageHistory(key="langchain_messages")

    model = ChatOpenAI(model_name="gpt-4o", temperature=0, streaming=True)
    contextualize_q_system_prompt="""Given a chat history and the latest user responses and questions \
    which might reference context in the chat history, formulate a short summary of the given information \
    which can be understood without the chat history."""
    contextualize_q_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", contextualize_q_system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human","{input}")
        ]
    )

    history_aware_retriever = create_history_aware_retriever(
        model, retriever, contextualize_q_prompt
    )

    st.session_state.product_info=load_summary_from_db(db, st.session_state.chat_id)
    st.session_state.det_product_info=load_info_from_db(db,st.session_state.chat_id)

    interview_system_prompt = create_prompt_template(st.session_state.det_product_info, st.session_state.product_info)

    interview_prompt= ChatPromptTemplate.from_messages(
        [
            ("system", interview_system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human","{input}")
    
        ]
    )

    interview_chain = create_stuff_documents_chain(model, interview_prompt)
    rag_chain = create_retrieval_chain(history_aware_retriever,interview_chain)

    conversational_rag_chain = RunnableWithMessageHistory( 
        rag_chain,
        lambda session_id: msgs,
        input_messages_key="input",
        history_messages_key="chat_history",
        output_messages_key="answer"
    )

    if len(msgs.messages)==0:
        first_prompt="Please welcome me and give me brief instructions on what to do and what to expect. Also give me a brief description of the product. "
        config = {"configurable": {"session_id": st.session_state['client_id']}}
        #st.chat_message("ai").write(conversational_rag_chain.invoke({"input": first_prompt}, config)['answer'])
        response = conversational_rag_chain.invoke({"input": first_prompt}, config)['answer']
        answer={"role":"ai", "input":response}
        st.session_state.answers.append(answer)

    for answer in st.session_state.answers:
        with st.chat_message(answer["role"]):
            st.markdown(answer["input"])

    if prompt := st.chat_input("Antworte hier..."):
        config = {"configurable": {"session_id": st.session_state['client_id']}}
        
        if "exit" in prompt:
            st.session_state.page="page2"
            sum_prompt="Write a detailed summary over the interview."
            st.session_state.sum_prompt=conversational_rag_chain.invoke({"input": sum_prompt}, config)['answer']
            save_interview_to_db(db, st.session_state['chat_id'], st.session_state['client_id'], st.session_state['sum_prompt'])
            #send_mail(st.session_state["sum_prompt"], email)
            st.rerun()

            
        st.session_state.answers.append({"role": "human", "input": prompt})

                
        with st.chat_message("human"):
                st.markdown(prompt)

        # Note: new messages are saved to history automatically by Langchain during run
        response = conversational_rag_chain.invoke({"input": prompt}, config)['answer']
        with st.chat_message("ai"):
            st.write_stream(split_response(response))
        #st.chat_message("ai").write(response)
        answer = {"role": "ai", "input": response}
        st.session_state.answers.append(answer)
  


def page1():
    st.session_state.chat_id=st.query_params["token"]
    if 'client_id' not in st.session_state: #client_id -> id for potential customer 
        st.session_state.client_id=str(uuid.uuid4())

    st.subheader("Willkommen in der FragenFabrik. Diese Anwendung wird Sie durch ein Interview über ein Produkt führen.")
    interview()

def page2():
    with st.container():
        st.subheader("Zusammenfassung Ihres Interviews:")
        st.write(st.session_state.sum_prompt)

if st.session_state.page == "page1":
    page1()
elif st.session_state.page == "page2":
    page2()