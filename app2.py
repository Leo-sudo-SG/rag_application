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
PINECONE_INDEX=os.environ['PINECONE_INDEX']
PINECONE_NAMESPACE_LLM2=os.environ['PINECONE_NAMESPACE_LLM2']
LANGCHAIN_TRACING_V2=os.environ['LANGCHAIN_TRACING_V2']
LANGCHAIN_ENDPOINT=os.environ['LANGCHAIN_ENDPOINT']
LANGCHAIN_API_KEY=os.environ['LANGCHAIN_API_KEY']
LANGCHAIN_PROJECT=os.environ['LANGCHAIN_PROJECT_LLM2']
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
    embedding=OpenAIEmbeddings()
    vectorstore = PineconeVectorStore(index_name=PINECONE_INDEX, embedding=embedding)
    retriever=vectorstore.as_retriever(
    search_kwargs={"namespace":PINECONE_NAMESPACE_LLM2,"k":2}
    )

    return retriever

def create_prompt_template(det_product_info,product_info):
    
    prompt_template="""
    Your name is "FragenFabrik".
    
    Task:
    As a helpful AI interview bot, your task is to conduct a user interview with a potential user about a product/service. 
    You are a professional for user-centred development and user expirience interviews. Your goal is to generate new knowledge about users, their experiences, needs and weaknesses.

    Instructions:
    You talk to a potential customer of the product/service.The information you collect will later be used for user-centred development of the product/service.
    Be careful not to ask questions twice or repeat yourself.
    First ask a few personal questions to be able to categorise the person in a group.
    Use this personal information to guide the rest of the interview.
    Make the interview interactive and add meaningful questions, for that use your common knowledge and extend it with the given questions from a questionaire.

    Useful questions:
    {context}

    Procedure:
    If there is no suitable question, ask your own question. If an answer is very short or incomplete, ask a follow-up question. 
    The questions should not be asked all at once, but alternate with the user's answers.
    For answers that have nothing to do with the question asked, try to re-enter the interview with a new question. 
    Only respond to enquiries that relate to your question and the context and do not provide information on other topics.
    Once all the questions have been asked, ask the product owner if they would like to add any further information and respond to their answer.
    At the end also point out that the interview can be concluded by entering "exit".
    If the user does not enter any further information, answer any further input with "Please type "exit" to finish the interview.".
    Only create a summary if exit has been entered by the user.
    Create a pure summary without a salutation or closing sentence after 'exit' has been entered.

    Interview context:
    As a context for your interview, you have a summary of an interview that was conducted with the product owner. 
    You ignore details in the following information specified with "Keine Angabe".
    Here you will find all the relevant information about the product that you should use to create the questions:\n
    """+product_info+"\n"+"Here is some essential information about the interview and the product that you should definitely use:\n"+det_product_info

    return prompt_template

def split_response(response):
     for word in response.split(" "):
        yield word + " "
        time.sleep(0.06)


def interview():
    
    retriever = load_retriever()
    msgs = StreamlitChatMessageHistory(key="langchain_messages")

    model = ChatOpenAI(model_name="gpt-4o", temperature=0, streaming=True)
    contextualize_q_system_prompt="""Given a chat history and the latest user response
    which might reference context in the chat history, formulate a possible follow-up question that can be understood without the chat history.
    Formulate this question allways in German."""
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

    st.subheader("Willkommen in der FragenFabrik. Diese Anwendung wird Sie durch ein Interview über ein Produkt oder eine Dienstleistung führen.")
    interview()

def page2():
    with st.container():
        st.subheader("Zusammenfassung Ihres Interviews:")
        st.write(st.session_state.sum_prompt)

if st.session_state.page == "page1":
    page1()
elif st.session_state.page == "page2":
    page2()
