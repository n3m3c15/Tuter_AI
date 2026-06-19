from KVerse_database_system.db_utils import structure, db_client
from KVerse_database_system.schemas import Subject_Document_kwargs
import pandas as pd

excel_path= r"C:\Users\kamal\Downloads\Subjects Catalogue - Kverse.xlsx"

def create_subject_documents(excel_path: str, collection_name: str = "Subject_Document"):
    excel_data = pd.read_excel(excel_path, sheet_name=None)
    
    inserted_docs = []
    for sheet_name, df in excel_data.items():
        grade = sheet_name[6:].strip()
        df = df.fillna("")  

        board_names = list(df.columns[1:])
        for _, row in df.iterrows():
            subject_name = str(row[df.columns[0]]).strip().lower().replace(" ", "_")
            if not subject_name:
                continue  
            for i, board in enumerate(board_names):
                board_clean = str(board).strip().lower().replace(" ", "_")
                book_name = str(row[df.columns[i + 1]]).strip()
                if not book_name:
                    continue
                subject_code = f"kverse-india-english-{board_clean}-{grade.lower()}-{subject_name}"
                existing = db_client[collection_name].find_one({"Subject_Code": subject_code})
                if existing:
                    continue
                doc =structure(
                    collection_name=collection_name,
                    schema=Subject_Document_kwargs,
                    Subject_Code=subject_code,
                    Medium="english",
                    Grade=grade,
                    Board=board_clean
                )

                inserted_docs.append(doc)
    return inserted_docs

create_subject_documents(excel_path)