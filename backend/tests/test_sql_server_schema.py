"""The Azure SQL tables must be able to hold Arabic text.

SQL Server turns a plain String into VARCHAR, which cannot store Arabic letters. These
tests build the table definitions for the SQL Server dialect (no server needed) and check
that every column that holds text typed by a person is NVARCHAR.
"""
from sqlalchemy.dialects import mssql
from sqlalchemy.schema import CreateTable

from app import models

PERSON_TEXT = {
    "users": {"email", "display_name"},
    "workspaces": {"name"},
    "documents": {"filename", "status_detail"},
    "document_segments": {"label", "text"},
}


def ddl(table) -> str:
    return str(CreateTable(table).compile(dialect=mssql.dialect()))


def column_types(table) -> dict[str, str]:
    dialect = mssql.dialect()
    return {c.name: c.type.compile(dialect=dialect) for c in table.columns}


def test_text_people_type_is_stored_as_unicode_on_sql_server():
    for table_name, names in PERSON_TEXT.items():
        types = column_types(models.Base.metadata.tables[table_name])
        for name in names:
            assert types[name].startswith("NVARCHAR"), (table_name, name, types[name])


def test_every_table_can_be_created_for_sql_server():
    for table in models.Base.metadata.sorted_tables:
        assert ddl(table).startswith("\nCREATE TABLE")
