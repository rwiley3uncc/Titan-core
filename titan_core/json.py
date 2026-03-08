{
  "description": "Titan Brain API Contract - Defines structured input and output format",

  "input_schema": {
    "user_id": "uuid-or-int",
    "role": "student | teacher | admin",
    "messages": [
      {
        "role": "user | assistant | system",
        "content": "string"
      }
    ],
    "tools": [
      "create_task",
      "save_memory",
      "draft_email",
      "create_note"
    ]
  },

  "output_schema": {
    "reply": "string",
    "proposed_actions": [
      {
        "type": "create_task",
        "args": {
          "title": "string",
          "due_at": "ISO8601 string or null"
        }
      },
      {
        "type": "save_memory",
        "args": {
          "tag": "string",
          "content": "string",
          "score_delta": "integer"
        }
      }
    ]
  }
}