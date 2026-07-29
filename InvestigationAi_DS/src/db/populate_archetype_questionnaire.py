import os
import openpyxl
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from archetype_models import Base, ArchetypeType, Archetype, InterviewQuestionnaire

DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/app"

EXCEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "Interview Questionnaire (2).xlsx",
)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()


def load_events_from_excel(path: str) -> list[tuple[str, str, str]]:
    """Return list of (archetype_name, definition, question) from the Events sheet."""
    wb = openpyxl.load_workbook(path)
    ws = wb["Events"]
    rows = []
    current_name = None
    current_def = None
    for row in ws.iter_rows(min_row=2, values_only=True):
        _, error_type, definition, question = row
        if error_type:
            current_name = str(error_type).strip()
            current_def = str(definition).strip() if definition else None
        if question and current_name:
            rows.append((current_name, current_def, str(question).strip()))
    return rows


# 1. Ensure archetype_type exists
archetype_type = session.query(ArchetypeType).filter_by(name="Interview Questionnaire").first()
if not archetype_type:
    archetype_type = ArchetypeType(name="Interview Questionnaire")
    session.add(archetype_type)
    session.commit()

# 2. Delete existing archetypes (and cascaded questionnaires) for this type
existing = session.query(Archetype).filter_by(archetype_type_id=archetype_type.id).all()
for arch in existing:
    session.query(InterviewQuestionnaire).filter_by(archetype_id=arch.id).delete()
    session.delete(arch)
session.commit()
print(f"Removed {len(existing)} existing archetype(s) for 'Interview Questionnaire'.")

# 3. Load new data from Excel
data = load_events_from_excel(EXCEL_PATH)

# 4. Insert new archetypes with definitions and questions
archetype_map: dict[str, Archetype] = {}
for name, definition, question in data:
    if name not in archetype_map:
        archetype = Archetype(
            name=name,
            definition=definition,
            archetype_type_id=archetype_type.id,
        )
        session.add(archetype)
        session.flush()
        archetype_map[name] = archetype
    else:
        archetype = archetype_map[name]
    session.add(InterviewQuestionnaire(description=question, archetype_id=archetype.id))

session.commit()
print(
    f"Populated {len(archetype_map)} archetype(s) with "
    f"{len(data)} question(s) from '{os.path.basename(EXCEL_PATH)}'."
)

