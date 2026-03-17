"""Universe domain layer.

Sub-modules
-----------
models
    Schema constants: RELATIONSHIP_TYPES, THESIS_TYPES, UPDATABLE_COMPANY_FIELDS
repository
    Direct SQL CRUD for company_master, company_relationships, company_thesis
service
    Higher-level operations combining repository calls (e.g. get_company_detail)
"""
