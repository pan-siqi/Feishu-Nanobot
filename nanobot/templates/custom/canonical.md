event name: {{ event_name }}
project: {{ project }}
aliases: {{ aliases | join(', ') if aliases else '' }}
status: {{ status }}
decision signal: {{ decision_signal }}
summary: {{ summary }}
decision result: {{ decision_result }}
entities: {{ entities | join('; ') if entities else '' }}
reasons: {{ reasons | join('; ') if reasons else '' }}
objections: {{ objections | join('; ') if objections else '' }}
alternatives: {{ alternatives | join('; ') if alternatives else '' }}
participants: {{ participants | join('; ') if participants else '' }}
deadline: {{ deadline or '' }}
importance: {{ importance }}
strength: {{ strength }}
review_count: {{ review_count }}
supersedes: {{ supersedes or '' }}
