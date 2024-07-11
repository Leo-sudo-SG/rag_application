#app3.py
from google.cloud import firestore
from google.oauth2 import service_account
from langchain_openai import ChatOpenAI
from langchain.chains.llm import LLMChain
from langchain.chains.combine_documents.stuff import StuffDocumentsChain
from langchain_core.prompts import PromptTemplate
from langchain_community.document_loaders import TextLoader
from langchain.schema.document import Document
from langchain.chains import MapReduceDocumentsChain, ReduceDocumentsChain
from langchain_text_splitters import CharacterTextSplitter
from langchain_core.output_parsers import StrOutputParser
from langsmith import Client
from urllib.parse import urlparse, parse_qs
from email_sending import send_mail
from database import load_email_from_db, fetch_combined_summary
import streamlit as st
import os
import json
import uuid


LANGCHAIN_TRACING_V2=os.environ['LANGCHAIN_TRACING_V2']
LANGCHAIN_ENDPOINT=os.environ['LANGCHAIN_ENDPOINT']
LANGCHAIN_API_KEY=os.environ['LANGCHAIN_API_KEY']
LANGCHAIN_PROJECT=os.environ['LANGCHAIN_PROJECT_LLM3']
OPENAI_API_KEY=os.environ['OPENAI_API_KEY']

client=Client()

key_dict = json.loads(st.secrets["textkey"])
creds = service_account.Credentials.from_service_account_info(key_dict)
db = firestore.Client(credentials=creds, project="llm-projekt")


st.title("FragenFabrik-Auswertung")

if 'page' not in st.session_state:
    st.session_state.page = "page1"



def summarize(token):

    llm = ChatOpenAI(model_name="gpt-4o", temperature=0, streaming=False)

    # Map
    map_template = """The following is a set of documents
    {docs}
    Based on this list of docs, please identify the main themes 
    Helpful Answer:"""
    map_prompt = PromptTemplate.from_template(map_template)
    map_chain = map_prompt | llm | StrOutputParser()

    # Reduce
    reduce_template = """The following is set of summaries:
    {docs}
    Take these and distill it into a final, consolidated summary of the main themes. 
    Helpful Answer:"""
    reduce_prompt = PromptTemplate.from_template(reduce_template)

    # Run chain
    reduce_chain = reduce_prompt | llm | StrOutputParser()

    # Takes a list of documents, combines them into a single string, and passes this to an LLMChain
    combine_documents_chain = StuffDocumentsChain(
        llm_chain=reduce_chain, document_variable_name="docs"
    )

    # Combines and iteratively reduces the mapped documents
    reduce_documents_chain = ReduceDocumentsChain(
        # This is final chain that is called.
        combine_documents_chain=combine_documents_chain,
        # If documents exceed context for `StuffDocumentsChain`
        collapse_documents_chain=combine_documents_chain,
        # The maximum number of tokens to group documents into.
        token_max=4000,
    )

    # Combining documents by mapping a chain over them, then combining results
    map_reduce_chain = MapReduceDocumentsChain(
        # Map chain
        llm_chain=map_chain,
        # Reduce chain
        reduce_documents_chain=reduce_documents_chain,
        # The variable name in the llm_chain to put the documents in
        document_variable_name="docs",
        # Return the results of the map steps in the output
        return_intermediate_steps=False,
    )

    text_splitter = CharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=1000, chunk_overlap=0
    )
    fetched_summary=fetch_combined_summary(db,token)
    #print(fetched_summary)
    docs = [Document(page_content=x) for x in text_splitter.split_text(fetched_summary)]

    result = map_reduce_chain.invoke(docs)["output_text"]
    try:
        send_mail(result,load_email_from_db(db,token))
        st.success('Email sent successfully!')
    except:
        st.error('Es ist ein Fehler aufgetreten. Bitte versuchen Sie es erneut.')

def validate_url(url):
    base_url = 'https://ragapplication-bkggtappynnyyzvyshq9mf7.streamlit.app/'
    
    # URL analysieren
    parsed_url = urlparse(url)
    
    # Überprüfen, ob das Scheme und der Netzwerkstandort (netloc) korrekt sind
    if parsed_url.scheme != 'https' or parsed_url.netloc != 'ragapplication-bkggtappynnyyzvyshq9mf7.streamlit.app':
        return False

    # Überprüfen, ob der Pfad leer oder '/' ist
    if parsed_url.path not in ['', '/']:
        return False

    # Abfrageparameter extrahieren
    query_params = parse_qs(parsed_url.query)

    # Überprüfen, ob der Token vorhanden und nicht leer ist
    token = query_params.get('token', [None])[0]
    if not token:
        return False

    # Überprüfen, ob der Token ein gültiger UUID4-String ist
    try:
        uuid_obj = uuid.UUID(token, version=4)
    except ValueError:
        return False

    # Überprüfen, ob der generierte UUID4 mit dem Original-Token übereinstimmt
    if str(uuid_obj) != token:
        return False

    return True



def page1():
    if url := st.text_input("Geben Sie hier den Link zu Ihrem Customer-Chatbot ein:",placeholder="https://ragapplication-bkggtappynnyyzvyshq9mf7.streamlit.app/?token=YourToken"):
        if(validate_url(url)):
            parsed_url = urlparse(url)
            query_params = parse_qs(parsed_url.query)
            token = query_params.get('token', [None])[0]
            summarize(token)
            st.session_state.page="page2"
            st.rerun()
        else:
            st.error('Fehlerhafter Link. Bitte überprüfen Sie Ihre Eingabe.')
    

def page2():
    st.write("Ihre Email wurde erfolgreich versendet!")

    
if st.session_state.page == "page1":
    page1()
elif st.session_state.page == "page2":
    page2()
