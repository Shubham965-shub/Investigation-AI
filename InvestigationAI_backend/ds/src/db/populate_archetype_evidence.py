import os
import openpyxl
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from archetype_models import Base, ArchetypeType, Archetype, Evidence

DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/app"

EXCEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "Evidence Library (4).xlsx",
)

engine = create_engine(DATABASE_URL)
Session = sessionmaker(bind=engine)
session = Session()


def load_evidences_from_excel(path: str) -> list[tuple[str, str, str]]:
    """Return list of (archetype_name, definition, evidence) from the Evidence Library sheet."""
    wb = openpyxl.load_workbook(path)
    ws = wb["Evidence Library"]
    rows = []
    current_name = None
    current_def = None
    for row in ws.iter_rows(min_row=2, values_only=True):
        _, failure_type, _qms_type, _type, _dept, definition, evidence = row[:7]
        if failure_type:
            current_name = str(failure_type).strip()
            current_def = str(definition).strip() if definition else None
        if evidence and current_name:
            rows.append((current_name, current_def, str(evidence).strip()))
    return rows


# 1. Ensure archetype_type exists
archetype_type = session.query(ArchetypeType).filter_by(name="Evidence Collection").first()
if not archetype_type:
    archetype_type = ArchetypeType(name="Evidence Collection")
    session.add(archetype_type)
    session.commit()

# 2. Delete existing archetypes (and cascaded evidences) for this type
existing = session.query(Archetype).filter_by(archetype_type_id=archetype_type.id).all()
for arch in existing:
    session.query(Evidence).filter_by(archetype_id=arch.id).delete()
    session.delete(arch)
session.commit()
print(f"Removed {len(existing)} existing archetype(s) for 'Evidence Collection'.")

# 3. Load new data from Excel
data = load_evidences_from_excel(EXCEL_PATH)

# 4. Insert new archetypes with definitions and evidence items
archetype_map: dict[str, Archetype] = {}
for name, definition, evidence in data:
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
    session.add(Evidence(description=evidence, archetype_id=archetype.id))

session.commit()
print(
    f"Populated {len(archetype_map)} archetype(s) with "
    f"{len(data)} evidence item(s) from '{os.path.basename(EXCEL_PATH)}'."
)
