"""The fields of the Excel imports of tags, frameworks and mappings (Slice 1.26, ADR 055).

Like ``import_fields`` for the curriculum: one list of field definitions makes the template and
checks the upload. Nothing here touches the database.
"""

from __future__ import annotations

from app.services.import_fields import Field, Kind, Sheet

# --- Tag lists and their values ---------------------------------------------------------------

TAG_ENTITY_WORDS = {
    "programme": "programme",
    "module": "module",
    "session": "learning_event",
    "objective": "objective",
}

TAG_LISTS = Sheet(
    "tag_lists",
    "Tag lists",
    "Lists of tags (teaching methods, assessment methods, themes, threads...). Institution-wide "
    "lists only: a faculty's own lists are managed on the Tag lists screen.",
    (
        Field(
            "key",
            "List key",
            Kind.TEXT,
            "Lower-case letters, digits, hyphens and underscores. It identifies the list: "
            "importing the same key again updates that list.",
            required=True,
            max_length=64,
        ),
        Field("name", "Name", Kind.TEXT, "The name people see.", required=True, max_length=255),
        Field(
            "kind",
            "Kind",
            Kind.CHOICE,
            "teaching_method, assessment_method, theme, thread, keyword, resource, epa or "
            "custom. It cannot be changed once the list exists.",
            required=True,
            choices="tag_kind",
        ),
        Field("description", "Description", Kind.LONG_TEXT, "Optional.", width=40),
        Field(
            "applies_to",
            "Applies to",
            Kind.REFERENCES,
            "Which items the list may tag, separated by semicolons: programme, module, session, "
            "objective. Blank means all of them.",
            width=30,
        ),
    ),
)

TAG_VALUES = Sheet(
    "tag_values",
    "Tag values",
    "The tags in each list. Importing a label that is already in the list updates it.",
    (
        Field(
            "list_key",
            "List key",
            Kind.REFERENCE,
            "The key of the list (on the Tag lists sheet or already in the installation).",
            required=True,
            max_length=64,
        ),
        Field("label", "Label", Kind.TEXT, "The tag.", required=True, max_length=255),
        Field(
            "code",
            "Code",
            Kind.TEXT,
            "An optional short code, unique in the list.",
            max_length=64,
            width=14,
        ),
        Field("description", "Description", Kind.LONG_TEXT, "Optional.", width=40),
    ),
)

TAG_SHEETS: tuple[Sheet, ...] = (TAG_LISTS, TAG_VALUES)
TAG_HOW = (
    "  Fill in the sheets you need; leave the others empty.",
    "  Upload the file on the Import page and read the preview. Nothing is changed until "
    "you confirm.",
    "  A list is matched by its List key, a tag by its Label within the list: importing again "
    "updates instead of duplicating. An import never deletes or deactivates anything.",
    "  A column you remove is left alone; a column you keep and leave blank clears that value.",
)

# --- Mappings ---------------------------------------------------------------------------------

MAPPINGS = Sheet(
    "mappings",
    "Mappings",
    "Links between objectives and framework items. Every row becomes a suggested link, to be "
    "reviewed like any other suggestion; an existing link is never changed.",
    (
        Field(
            "objective",
            "Objective (External ID)",
            Kind.REFERENCE,
            "The External ID of the objective in this version (set by the curriculum import).",
            required=True,
            width=24,
        ),
        Field(
            "framework",
            "Framework key",
            Kind.TEXT,
            "The key of the framework (for example hpcsa-core). Its active version is used "
            "unless a Framework version is given.",
            required=True,
            max_length=64,
        ),
        Field(
            "framework_version",
            "Framework version",
            Kind.TEXT,
            "Optional: the version label, when the active version is not the one meant.",
            max_length=64,
            width=14,
        ),
        Field(
            "code",
            "Framework item code",
            Kind.TEXT,
            "The code of the item in the framework.",
            required=True,
            max_length=64,
            width=22,
        ),
        Field(
            "coverage",
            "Coverage (1-5)",
            Kind.INTEGER,
            "How much of this one item this one objective covers: 1 = 1 to 20% ... 5 = 81 to 100%.",
            required=True,
            minimum=1,
            maximum=5,
            width=12,
        ),
        Field(
            "depth",
            "Depth",
            Kind.CHOICE,
            "below, matches, above or not_applicable. Blank means matches.",
            choices="depth",
            width=14,
        ),
        Field(
            "rationale",
            "Reason",
            Kind.LONG_TEXT,
            "Optional, at most 1000 characters.",
            max_length=1000,
            width=50,
        ),
        Field(
            "status",
            "Status",
            Kind.TEXT,
            "Written by an export (accepted, suggested...). An import ignores it.",
            max_length=32,
            width=14,
        ),
    ),
)

MAPPING_SHEETS: tuple[Sheet, ...] = (MAPPINGS,)
MAPPING_HOW = (
    "  Fill in the Mappings sheet. Upload the file on the Import page and read the preview. "
    "Nothing is changed until you confirm. Only draft versions can be imported into.",
    "  Every row becomes a suggested link made by you with the source 'import'. It is not "
    "accepted: a reviewer decides on it in the review queue.",
    "  A pair that is already linked (in any state, rejected included) is left as it is.",
)

# --- Frameworks -------------------------------------------------------------------------------

FRAMEWORK = Sheet(
    "framework",
    "Framework",
    "The framework itself: one row.",
    (
        Field(
            "key",
            "Key",
            Kind.TEXT,
            "Lower-case letters, digits and hyphens: it identifies the framework across versions.",
            required=True,
            max_length=64,
            width=18,
        ),
        Field("name", "Name", Kind.TEXT, "The framework's name.", required=True, max_length=255),
        Field(
            "version",
            "Version",
            Kind.TEXT,
            "The version label (for example 2024).",
            required=True,
            max_length=64,
            width=12,
        ),
        Field(
            "publisher",
            "Publisher",
            Kind.TEXT,
            "Who publishes it.",
            required=True,
            max_length=255,
        ),
        Field(
            "licence",
            "Licence note",
            Kind.TEXT,
            "How the text may be used.",
            max_length=1000,
            width=30,
        ),
        Field(
            "profile",
            "Profile",
            Kind.CHOICE,
            "core, health or other. Blank means core.",
            choices="framework_profile",
            width=12,
        ),
        Field("url", "Web address", Kind.TEXT, "Optional.", max_length=2048),
        Field("description", "Description", Kind.LONG_TEXT, "Optional.", width=40),
    ),
)

FRAMEWORK_ITEMS = Sheet(
    "items",
    "Items",
    "The items of the framework, in order.",
    (
        Field(
            "code",
            "Code",
            Kind.TEXT,
            "The item's code, unique in the framework.",
            required=True,
            max_length=64,
            width=16,
        ),
        Field("title", "Title", Kind.LONG_TEXT, "The item's wording.", required=True, width=70),
        Field("description", "Description", Kind.LONG_TEXT, "Optional.", width=40),
        Field(
            "parent_code",
            "Parent code",
            Kind.REFERENCE,
            "The code of the item this one belongs under; blank for a top-level item.",
            max_length=64,
            width=16,
        ),
    ),
)

FRAMEWORK_SHEETS: tuple[Sheet, ...] = (FRAMEWORK, FRAMEWORK_ITEMS)
FRAMEWORK_HOW = (
    "  Fill in the Framework sheet (one row) and the Items sheet.",
    "  Upload the file on the Import page. It is checked like a framework pack file and you see "
    "the same preview before anything is imported.",
    "  Only the framework's own wording belongs here. Check the licence of what you copy.",
)
