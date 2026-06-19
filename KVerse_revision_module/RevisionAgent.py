from KVerse_database_system.db_config import db_client
from KVerse_database_system import db_utils
from datetime import datetime
from KVerse_language_engine.agent import GPTAgent
from pydantic import PrivateAttr


class RevisionAgent(GPTAgent):
    messages: list
    subject_code: str

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def build_conversation_from_history(self, session_id):
        message_docs = db_utils.retrieve_document("Message_Document", multiple_keys={"Session_Id": session_id})
        # try:
        #     _ = db_utils.create_collection("Revision_Document")
        # except Exception as e:
        #     pass   ## document expected to exist
        session_doc = db_utils.retrieve_document("Session_Document", primary_key=session_id)[0]
        if not session_doc:
            raise ValueError(f"Session with ID '{session_id}' does not exist")
        self.subject_code = session_doc['Subject_Code']
        # print(f'Subject Code: {self.subject_code}, User ID: {self.user_id}')
        matched_doc = session_doc.get('Summary')
        # print(f'revision_doc: {revision_doc}')
        # print(f'matched_doc: {matched_doc}')
        if matched_doc:
            previously_used_messages = matched_doc.get('Included_Message_Ids', [])
        else:
            previously_used_messages = []

        # print(f"Prev_Msg_Ids : {previously_used_messages}")
        conversation = ''
        new_msg_ids = []
        for doc in message_docs:
            if doc['Message_Id'] not in previously_used_messages:
                new_msg_ids.append(doc['Message_Id'])
        if new_msg_ids == []:
            # print("No new messages to include in the revision sheet.")
            return None, None
        new_message_docs = [doc for doc in message_docs if doc['Message_Id'] in new_msg_ids]
        for doc in new_message_docs:
            if 'Query' in doc['Message'].keys():
                conversation += f"User: {doc['Message']['Query']}\n"
                previously_used_messages.append(doc['Message_Id'])
            elif 'Solution' in doc['Message'].keys():
                conversation += f"Agent: {doc['Message']['Solution']}\n"
                previously_used_messages.append(doc['Message_Id'])
        updated_incl_messages = previously_used_messages
        print(f'New Message IDs for Revision Sheet: {new_msg_ids}')
        return conversation, updated_incl_messages

    def generate_query(self, session_id):
        conversation, updated_incl_msgs = self.build_conversation_from_history(session_id)
        revision_doc = db_utils.retrieve_document("Session_Document", primary_key=session_id)[0]
        # for doc in revision_doc:
        #     for session in doc.get("Sessions", []):
        #         if session.get("Session_Id") == session_id:
        #             matched_doc.append(session)
        if not conversation:
            prev_summary = revision_doc['Summary']['Revision_Sheet'] if revision_doc['Summary'] else None
            return prev_summary, None

        previous_revision_sheet = revision_doc.get('Summary', {}).get('Revision_Sheet', '')
        print(previous_revision_sheet)
        print(f'Previous Revision Sheet: {previous_revision_sheet}')
        if previous_revision_sheet:
            self.messages.append(
                {"role": "system",
                 "content": [{
                     "type": "text", "text": f"Here is the previous revision sheet: {previous_revision_sheet}"}]
                 }
            )
        query = f"Given the previous revision sheet: {previous_revision_sheet}, please provide a Neatly formatted point wise summary of the following conversation, Make sure all important points are covered.\n\nConversation:\n{conversation}"
        return query, updated_incl_msgs

    def update_revision_sheet(self, session_id, revision_sheet, updated_incl_msgs):
        summary = {
            "Revision_Sheet": revision_sheet,
            "Included_Message_Ids": updated_incl_msgs,
            "Last_Updated": datetime.now()
        }

        try:
            _ = db_utils.update_document("Session_Document",
                                         query={"User_Id": self.user_id, "Subject_Code": self.subject_code,
                                                "Session_Id": session_id},
                                         updates={"Summary": summary
                                                  })
        except Exception as e:
            _ = db_client['Session_Document'].update_one(
                {"Session_Id": session_id},
                {"$set": {"Summary": summary}},
                upsert=True
            )



