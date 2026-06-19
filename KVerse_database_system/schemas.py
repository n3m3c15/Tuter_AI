# Schema for MongoDB Collections
import datetime

primary_key_dict = {
    "Subject_Document": "Subject_Code",
    "Session_Document": "Session_Id",
    "Message_Document": "Message_Id",
    "User_Document": "user_id",
    "Quiz_Document": "Quiz_Id",
    "Question_Document": "Question_Id",
    "Session_State_Document": "Session_Id",

}
Subject_Document_kwargs ={
    "Subject_Code": "subject_code",
    "Medium": "medium",
    "Grade": "grade",
    "Board": "board",
    "Vector_Index": "vector_index",
    "Graph_Id": "graph_id",
}

User_Message_Structure_kwargs = {
    "Query": "query",
    "Attachment": "attachment",
    "Attachment_Type": "attachment_type",
    "Special_Type": "special_type",
    "Remark_Flag": "remark_flag",
    "Reply_Message_Id": "reply_message_id",
}

message_kwargs = {
    "sid": "sid",
    "query": "query",
    "image_url_BB": "output_image_url",
    "cropped_img_noBB": "cropped_image_url",
    "diag_urls": "diag_urls",
    "Bounding_Box": "Bounding_Box",
    "Extracted_questions": None,
    "mid": "mid"
}

Message_Document_kwargs = {
    "Message_Id": "message_id",
    "Session_Id": "session_id",
    "Message": "message_content",
    "Message_Sender": "sender",
    "Inputs": "inputs",
    "Root_Message_Id": "root_message_id",
    "Parent_Message_Id": "parent_message_id",
    "Child_Message_Ids": "child_message_ids",
    "Created_At": "created_at",
}

Session_Document_kwargs = {
    "Session_Id": "Session_Id",
    "User_Id": "User_Id",
    "Generated_Name": "generated_name",
    "Subject_Code": "Subject_Code",
    "Created_At": str(datetime.datetime.now()),
}

