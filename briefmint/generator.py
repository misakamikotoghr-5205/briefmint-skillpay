"""Source-bounded brief generation. No model calls or invented market facts."""
import hashlib
import json


class InputError(ValueError):
    pass


def normalize_request(data):
    if not isinstance(data, dict):
        raise InputError('request must be a JSON object')
    allowed = {'title', 'audience', 'objective', 'deliverables', 'constraints', 'facts'}
    if set(data) - allowed:
        raise InputError('unknown request fields: ' + ', '.join(sorted(set(data) - allowed)))
    result = {}
    for key in ('title', 'audience', 'objective'):
        value = data.get(key)
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 500:
            raise InputError(f'{key} must contain 1–500 characters')
        result[key] = value.strip()
    for key in ('deliverables', 'constraints'):
        value = data.get(key, [])
        if not isinstance(value, list) or len(value) > 20:
            raise InputError(f'{key} must be an array with at most 20 items')
        if any(not isinstance(item, str) or not 1 <= len(item.strip()) <= 500 for item in value):
            raise InputError(f'{key} items must contain 1–500 characters')
        result[key] = list(dict.fromkeys(item.strip() for item in value))
    facts = data.get('facts', [])
    if not isinstance(facts, list) or len(facts) > 30:
        raise InputError('facts must be an array with at most 30 items')
    result['facts'] = []
    for fact in facts:
        if not isinstance(fact, dict) or set(fact) - {'text', 'source'}:
            raise InputError('each fact must contain text and an optional source')
        text, source = fact.get('text'), fact.get('source', '')
        if not isinstance(text, str) or not 1 <= len(text.strip()) <= 1000:
            raise InputError('fact text must contain 1–1,000 characters')
        if not isinstance(source, str) or len(source) > 1000:
            raise InputError('fact source must be a string of at most 1,000 characters')
        result['facts'].append({'text': text.strip(), 'source': source.strip()})
    return result


def request_hash(data):
    normalized = normalize_request(data)
    return hashlib.sha256(json.dumps(normalized, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def generate_brief(data):
    request = normalize_request(data)
    facts = [{'id': f'F{index + 1}', **fact, 'verification': 'user-provided; not independently verified'}
             for index, fact in enumerate(request['facts'])]
    missing = []
    if not request['deliverables']:
        missing.append('Confirm the exact deliverable formats and acceptance owner.')
    if not request['constraints']:
        missing.append('Confirm the budget, timeline, and delivery constraints.')
    if not facts:
        missing.append('Provide evidence for the customer problem before making market claims.')
    if any(not fact['source'] for fact in facts):
        missing.append('Add provenance to facts that do not yet have a source.')
    questions = missing + ['Who signs off on the final deliverables?', 'What observable outcome will demonstrate success?']
    scope = request['deliverables'] or ['A proposed deliverable list for the owner to approve']
    brief = {
        'version': 1,
        'title': request['title'],
        'audience': request['audience'],
        'objective': request['objective'],
        'summary': f"Create {request['title']} for {request['audience']}. The intended outcome is: {request['objective']}",
        'scope': {'included': scope, 'excluded': ['Unspecified work or claims unsupported by the supplied facts']},
        'constraints': request['constraints'],
        'evidenceLedger': facts,
        'assumptions': ['No external research was performed.', 'User-provided facts require owner review before publication.'],
        'acceptanceCriteria': [f'Owner approves: {item}' for item in scope]
            + ['Every factual claim traces to a supplied fact or is explicitly labeled as an assumption.',
               'The acceptance owner confirms alignment with the stated objective.'],
        'plan': [
            {'step': 1, 'activity': 'Resolve open decisions', 'output': 'Approved scope, owner, and constraints'},
            {'step': 2, 'activity': 'Produce the agreed deliverables', 'output': scope},
            {'step': 3, 'activity': 'Review evidence and acceptance criteria', 'output': 'Owner-reviewed handoff'},
        ],
        'risks': [{'severity': 'review', 'issue': question, 'response': 'Resolve with the project owner.'} for question in missing],
        'openQuestions': questions,
        'advisors': [
            {'role': 'analyst', 'mode': 'deterministic-rules', 'finding': f'{len(facts)} supplied facts, {len(scope)} scoped deliverables.'},
            {'role': 'skeptic', 'mode': 'deterministic-rules', 'finding': f'{len(missing)} information gaps require owner review.'},
            {'role': 'editor', 'mode': 'deterministic-rules', 'finding': 'Scope, evidence, acceptance criteria, and next decisions are separated.'},
        ],
        'generator': {'mode': 'deterministic-template', 'llmUsed': False, 'inputSha256': request_hash(request)},
    }
    lines = [f"# {brief['title']}", '', f"**Audience:** {brief['audience']}", '', brief['summary'], '', '## Scope', '']
    lines.extend(f'- {item}' for item in scope)
    lines += ['', '## Constraints', ''] + [f'- {item}' for item in (brief['constraints'] or ['To be confirmed'])]
    lines += ['', '## Evidence', '']
    lines.extend(f"- [{fact['id']}] {fact['text']} (Source: {fact['source'] or 'not supplied'}; user-provided)" for fact in facts)
    if not facts:
        lines.append('No supporting facts supplied; do not infer market or performance claims.')
    lines += ['', '## Acceptance criteria', ''] + [f'- [ ] {item}' for item in brief['acceptanceCriteria']]
    lines += ['', '## Open decisions', ''] + [f'- {item}' for item in questions]
    lines += ['', '*Generated locally with deterministic rules. No LLM or external research was used.*', '']
    brief['markdown'] = '\n'.join(lines)
    return brief
