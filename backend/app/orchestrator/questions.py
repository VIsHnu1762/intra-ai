"""Concrete spoken assessment objectives, independent of persona names.

These are bounded fallback objectives, not generated variations of M1 gap labels.
The same objective ID survives changes in wording, evidence subject and difficulty.
"""
from __future__ import annotations

import re
from typing import Any

from app.models.enums import DifficultyLevel


_QUESTIONS: dict[str, tuple[str, str, str, str]] = {
    'technical_depth': (
        'What did your code need to do in one project?',
        'What input did code you worked on receive?',
        'How did you check the output of code you worked on was correct?',
        'What limitation did you discover in code you worked on?',
    ),
    'system_design': (
        'For a small web app, where would you store its user data?',
        'How would a login request from a web app reach its database?',
        'How would you check whether the database is causing slow requests?',
        'What should happen if that database becomes unavailable?',
    ),
    'software_architecture': (
        'In a web app, what job does the database do?',
        'Why might you separate the user interface from the database?',
        'How would you test the database code separately?',
        'What change would make you split one service into two?',
    ),
    'coding_problem_solving': (
        'Given a list containing 2 and 3, how would a loop calculate their total?',
        'How would a function that sums a list handle an empty list?',
        'What test would catch a function adding the same list item twice?',
        'How would you find a duplicate value without comparing every pair?',
    ),
    'scalability': (
        'Imagine a web app gets twice as many users. What would you check first?',
        'How could a cache reduce repeated database reads?',
        'How would you check whether adding another server helped?',
        'What could make one server receive much more work than the others?',
    ),
    'debugging': (
        'If your program prints the wrong result, what would you check first?',
        'How would you reproduce a bug that happens only sometimes?',
        'What test would show that your fix worked?',
        'How would you investigate a failure that appears only under heavy load?',
    ),
    'technical_decision_making': (
        'What was one tool you chose for a project?',
        'Why did you choose a tool you used over one alternative?',
        'How did you check that the choice met your needs?',
        'What new constraint would make you reconsider that choice?',
    ),
    'product_sense': (
        'Who was the main user of a project you worked on?',
        'What problem did your project\'s users need you to solve?',
        'How did you check whether the feature helped that user?',
        'What user need did you decide to leave out of the first release?',
    ),
    'customer_understanding': (
        'What was one difficulty a user had before your project?',
        'How did you learn what users found difficult before your project?',
        'How would you check whether other users have the same problem?',
        'How would you resolve conflicting feedback from two types of user?',
    ),
    'customer_impact': (
        'What became easier for the user after your feature was released?',
        'What number could show whether the feature helped?',
        'How would you check whether the improvement came from your feature?',
        'What negative effect would make you reconsider the release?',
    ),
    'problem_identification': (
        'What problem was your project intended to solve?',
        'What made the problem your project addressed worth solving first?',
        'How would you check that you identified the underlying cause?',
        'What evidence would make you change your understanding of the problem?',
    ),
    'prioritization': (
        'If you had one day, would you fix a crash or add a feature?',
        'What information would help you choose between two user requests?',
        'How would you check whether your first priority was the right one?',
        'What would make you change priorities halfway through a release?',
    ),
    'product_strategy': (
        'What was the main goal of your project?',
        'Which feature contributed most directly to your project\'s main goal?',
        'How would you check progress toward that goal?',
        'What evidence would make you change the product direction?',
    ),
    'requirements_thinking': (
        'What did the user need the feature to do?',
        'How would you turn a user\'s request for faster search into one testable requirement?',
        'How would you check that the completed feature meets the requirement?',
        'How would you resolve a requirement that conflicts with a deadline?',
    ),
    'trade_off_decisions': (
        'With one day available, would you fix a crash or improve the page design?',
        'What would you give up by adding a feature before fixing a crash?',
        'How would you check whether your choice was worthwhile?',
        'What evidence would make you reverse that decision?',
    ),
    'metrics_and_roi': (
        'What number could show whether users find a feature useful?',
        'How would you measure how often people use search before improving it?',
        'How would you check that an increase reflects a real improvement?',
        'What cost would you compare against the benefit of that feature?',
    ),
    'market_understanding': (
        'Who would most benefit from your product?',
        'What alternative to your product could its users choose today?',
        'How would you check whether they prefer your solution?',
        'What market change would make you reconsider your target users?',
    ),
    'communication_of_product_decisions': (
        'How would you tell a teammate that a release will be delayed?',
        'How would you explain your chosen priority to someone who disagrees?',
        'How would you check that everyone understood the decision?',
        'How would you handle a disagreement between a customer and the engineering team?',
    ),
}


def objective_questions(competency: str, difficulty: DifficultyLevel) -> list[tuple[str, str]]:
    questions = _QUESTIONS.get(competency)
    if questions is None:
        topic = competency.replace('_', ' ')
        questions = (
            f'Think of a task involving {topic}. What did you need to achieve?',
            f'For that {topic} task, what was your first step?',
            f'How did you check whether the {topic} task succeeded?',
            f'What constraint made that {topic} task harder?',
        )
    ids = ('purpose', 'apply', 'verify', 'limits')
    # Stronger candidates begin with application; weak candidates get a
    # concrete fundamental first. The finite identities never change.
    order = (0, 1, 2, 3) if difficulty == DifficultyLevel.EASY else (1, 2, 3, 0)
    return [(f'{competency}:{ids[i]}', questions[i]) for i in order]


def targeted_gap_objective(competency: str, gaps: list[str]) -> tuple[str, str] | None:
    """Translate supported technical gaps into one concrete bounded objective.

    Variants retain the same objective identity, so changing a gap label cannot
    create another attempt. EASY questions deliberately use the basic bank.
    """
    if competency not in {'system_design', 'software_architecture', 'scalability',
                          'technical_depth', 'debugging', 'technical_decision_making'}:
        return None
    text = ' '.join(gaps).casefold()
    if re.search(r'invalidat|stale\s+(?:cache|data|value)', text):
        return f'{competency}:apply', 'How would you handle cache invalidation when a database value changes?'
    if 'idempoten' in text or 'duplicate' in text:
        return f'{competency}:apply', 'How would you keep a retried payment from being charged twice?'
    if 'thread dump' in text or 'deadlock' in text:
        return f'{competency}:verify', 'What would you look for in a thread dump when a server stops responding?'
    if 'partition' in text:
        return f'{competency}:limits', 'If two servers cannot communicate, how would you prevent conflicting writes?'
    if re.search(r'failure|recovery|partition|consistency|crash', text):
        return f'{competency}:limits', 'After a server failure, how would you check whether its last database write succeeded?'
    if re.search(r'latency|throughput|performance|metric', text):
        return f'{competency}:verify', 'How would you measure whether a change made a web request faster?'
    return None


_SECOND_REQUEST = re.compile(
    r',?\s+and\s+(?:then\s+|also\s+)?(?=(?:how|what|why|which|where|when|can|could|would|will|do|did|is|are|'
    r'explain|describe|outline|clarify|list|compare|summarize|tell\s+me|walk\s+me\s+through)\b)',
    re.I,
)
_ACKNOWLEDGEMENT = re.compile(
    r"^(?:thanks|thank you|that sounds interesting|that(?:'|’)s interesting|"
    r'that makes sense|got it|understood)[.!]\s+', re.I,
)
_BROAD_EASY_SCOPE = re.compile(
    r'\b(?:walk\s+me\s+through|describe|explain|outline|summari[sz]e|what\s+is)\s+'
    r'(?:(?:the|your|its|that)\s+)?(?:(?:high[- ]level|overall|end[- ]to[- ]end|full|entire)\s+(?:system\s+)?'
    r'(?:architecture|design)|(?:architecture|design)\s+of\s+(?:the\s+|your\s+)?entire\s+system)\b',
    re.I,
)


def spoken_question_is_clear(question: str, difficulty: DifficultyLevel) -> bool:
    """Reject compound checklists and abstract internal evaluation labels."""
    limit = 32 if difficulty == DifficultyLevel.EASY else 48
    return bool(question.strip()) and (
        len(question.split()) <= limit
        and question.count('?') == 1
        and question.count(',') < 2
        and ';' not in question
        and not _SECOND_REQUEST.search(question)
        and not (difficulty == DifficultyLevel.EASY and _BROAD_EASY_SCOPE.search(question))
        and not re.search(r'\b(?:core concepts of|example of concrete|example of specific|technical depth|product sense)\b', question, re.I)
    )


def first_spoken_question(question: str, difficulty: DifficultyLevel) -> str | None:
    """Keep the first complete model-authored question when it bundles two.

    Only acknowledgement-only prefixes and explicit second request clauses can
    be removed. Scenario statements are retained by refusing the split rather
    than losing their context. The remaining question must still be clear at
    the requested difficulty; extracting a broad architecture question does
    not make it an accessible EASY question.
    """
    question = _ACKNOWLEDGEMENT.sub('', question.strip(), count=1)
    if not re.match(r'^(?:how|what|why|where|when|which|can|could|would|will|do|did|is|are)\b', question, re.I):
        return None
    parts = _SECOND_REQUEST.split(question, maxsplit=1)
    if len(parts) < 2:
        return None
    first = parts[0].rstrip(' ,?.') + '?'
    return first if spoken_question_is_clear(first, difficulty) else None


_TARGET_STOP_WORDS = frozenset(
    'a an the this that it its your our my you i we they their one some any what which '
    'how why where when can could would should does did do is are was were be been '
    'have has had to from with for of in on at as by and or but about mentioned '
    'specific exact particular please tell explain describe application app project '
    'software system part component'.split()
)


def _information_words(value: str) -> set[str]:
    return {word.casefold().removesuffix('s') for word in re.findall(r"[\w]+", value)
            if len(word) > 2 and word.casefold() not in _TARGET_STOP_WORDS}


def validate_follow_up_contract(value: Any, current_answer: str) -> tuple[dict[str, str] | None, str | None]:
    """Validate the bounded information plan without another inference request.

    Exact source anchoring and a single short target are enforceable here;
    these structural checks do not claim to prove all semantic relevance.
    """
    if not isinstance(value, dict):
        return None, 'invalid_shape'
    keys = ('answer_anchor', 'information_target', 'expected_answer', 'objective')
    if any(not isinstance(value.get(key), str) or not value[key].strip() for key in keys):
        return None, 'missing_fields'
    contract = {key: ' '.join(value[key].split()) for key in keys}
    anchor, target, expected = (contract[key] for key in keys[:3])
    normalized_answer = ' '.join(current_answer.split()).casefold()
    # Word boundaries prevent an anchor such as "auth" being invented from
    # "authentication". Preserve punctuation inside the actual quoted phrase.
    if (not normalized_answer or len(anchor.split()) > 16 or len(anchor) > 200
            or not re.search(r'(?<!\w)' + re.escape(anchor.casefold()) + r'(?!\w)', normalized_answer)
            or not _information_words(anchor)):
        return None, 'anchor_not_in_answer'
    if (not 3 <= len(target.split()) <= 16 or len(target) > 180
            or re.search(r'[?!.;:\n]|\b(?:and|or)\b', target, re.I)
            or re.match(r'^(?:what|which|how|why|where|when|explain|describe|list|tell|you|i|we)\b', target, re.I)
            or not _information_words(target)):
        return None, 'target_not_single_fact'
    if (len(expected.split()) > 12 or len(expected) > 120
            or re.search(r'[?!.;:\n]|\b(?:and|or|all|overview|walkthrough|end.to.end|whole|entire)\b', expected, re.I)
            or not _information_words(expected)):
        return None, 'unbounded_expected_answer'
    if contract['objective'] not in {'purpose', 'apply', 'verify', 'limits'}:
        return None, 'invalid_objective'
    return contract, None


def question_matches_follow_up(question: str, contract: dict[str, str]) -> bool:
    """Require an informative link to the selected fact, not boilerplate words."""
    return bool(_information_words(question) & (
        _information_words(contract['answer_anchor']) | _information_words(contract['information_target'])))


def question_has_unspecified_scope(question: str) -> bool:
    """Flag a whole-project failure/walkthrough with no named unit of work.

    Used for generated prose before trying its fact-level plan or M1's probe;
    the established fallback bank remains explicitly labelled as fallback.
    """
    return bool(
        _BROAD_EASY_SCOPE.search(question)
        or re.search(r'\b(?:one|some|any)\s+(?:part|component)\b.*\b(?:fail|stop|break|working)', question, re.I)
        or re.search(r'\b(?:app|application|project|system|LMS)\b.{0,35}\b(?:wrong|incorrect)\s+result\b', question, re.I)
        or re.search(r'\b(?:how|walk)\b.{0,30}\b(?:one|a|any)\s+request\b.{0,35}\b(?:move|travel|through)\b', question, re.I)
    )


def repair_follow_up_question(contract: dict[str, str], difficulty: DifficultyLevel) -> str | None:
    """Render the already validated fact plan, without inventing a new topic."""
    anchor = contract['answer_anchor'].rstrip(' .?!')
    target = contract['information_target']
    if not re.match(r'^(?:a|an|the|one|your|their|its|our|this|that|each)\b', target, re.I):
        target = f'the {target}'
    question = f"You mentioned {anchor}. What is {target}?"
    return question if (spoken_question_is_clear(question, difficulty)
                        and not question_has_unspecified_scope(question)) else None


def information_target_was_asked(contract: dict[str, str], history: list[Any]) -> bool:
    """Keep the same fact closed even when its question or anchor is reworded."""
    target = _information_words(contract['information_target'])
    for item in history:
        previous = item.metadata.get('follow_up')
        if not isinstance(previous, dict) or not isinstance(previous.get('information_target'), str):
            continue
        old_target = _information_words(previous['information_target'])
        if target and old_target and target == old_target:
            return True
    return False
