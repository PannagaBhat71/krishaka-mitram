import re
import phonenumbers
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional
from django.conf import settings
from .models import FilterRule


@dataclass
class DetectedViolation:
    rule_type: str
    rule_name: str
    detected_text: str
    severity: str
    action: str
    start_idx: int = -1
    end_idx: int = -1
    context: str = ""


@dataclass
class FilterResult:
    is_clean: bool
    violations: List[DetectedViolation] = field(default_factory=list)
    filtered_content: str = ""
    original_content: str = ""
    should_block: bool = False
    should_warn: bool = False
    filter_types: List[str] = field(default_factory=list)

    @property
    def is_filtered(self) -> bool:
        """Return True if the message was filtered (i.e., not clean)."""
        return not self.is_clean


class MessageFilteringEngine:
    """
    Comprehensive rule-based and regex heuristic filtering engine for
    detecting sensitive personal information, external contact sharing,
    financial identifiers, URLs, and prohibited keywords in Krishaka Mitram chat.
    """

    # --- REGEX PATTERNS ---

    # Word-to-digit dictionary for written number detection
    WORD_DIGITS = {
        'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
        'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
        'ondhu': '1', 'eradu': '2', 'mooru': '3', 'naalku': '4', 'aidhu': '5',
        'aaru': '6', 'elu': '7', 'entu': '8', 'ombhatthu': '9', 'ombatthu': '9', 'sonne': '0'
    }

    # Indian Phone Regex: 10 digits starting with 6-9, with optional +91/0 prefix and delimiters
    PHONE_REGEX = re.compile(
        r'(?:(?:\+?91[\s\-\.]?)|(?:0))?[6-9]\d{2}[\s\-\.]?\d{3}[\s\-\.]?\d{4}\b|'
        r'\b[6-9]\d{9}\b|'
        r'\b[6-9](?:[\s\-\.\(\)]*\d){9}\b',
        re.IGNORECASE
    )

    # Standard Email Regex
    EMAIL_REGEX = re.compile(
        r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
        re.IGNORECASE
    )

    # Obfuscated Email Regex (e.g. user [at] gmail [dot] com or user at domain dot in)
    OBFUSCATED_EMAIL_REGEX = re.compile(
        r'\b[A-Za-z0-9._%+-]+\s*(?:\[at\]|\(at\)|@|\bat\b)\s*[A-Za-z0-9.-]+\s*(?:\[dot\]|\(dot\)|\.|\bdot\b)\s*(?:com|in|org|net|co|io|edu|gov|ac|org\.in|co\.in)\b',
        re.IGNORECASE
    )

    # UPI VPA Regex (e.g. user@okhdfcbank, 9876543210@paytm, user@ybl, name@upi, abc@axl, etc.)
    UPI_HANDLES = (
        r'(?:okhdfcbank|okaxis|oksbi|okicici|ybl|ibl|axl|paytm|upi|apl|icici|'
        r'sbi|hdfcbank|axisbank|barodampay|pnb|cnrb|federal|boi|kotak|postbank|'
        r'aubank|freecharge|airtel|jupiteraxis|idfcbank|yesbank|dbs)'
    )
    UPI_REGEX = re.compile(
        rf'\b[A-Za-z0-9.\-_]{{2,64}}@(?:{UPI_HANDLES})\b|'
        r'\b[A-Za-z0-9.\-_]{2,64}@upi\b|'
        r'\b\d{10}@(paytm|upi|ybl|okhdfcbank|okaxis|oksbi|okicici)\b',
        re.IGNORECASE
    )

    # Obfuscated UPI (e.g., "my upi is tejas at okaxis" or "upi 9876543210 @ paytm")
    OBFUSCATED_UPI_REGEX = re.compile(
        rf'\b(?:upi|gpay|phonepe|paytm)[\s:]*([A-Za-z0-9.\-_]+)\s*(?:@|\bat\b)\s*(?:{UPI_HANDLES}|upi)\b|'
        rf'\b(?:my\s+)?upi\s+(?:is|id|vpa)?\s*([A-Za-z0-9.\-_]+)\s*(?:@|\bat\b)\s*(?:{UPI_HANDLES}|upi)\b',
        re.IGNORECASE
    )

    # Indian IFSC Code: 4 alphabets + '0' + 6 alphanumeric
    IFSC_REGEX = re.compile(
        r'\b[A-Z]{4}0[A-Z0-9]{6}\b',
        re.IGNORECASE
    )

    # Bank Account Contextual Regex: 9-18 digits near keywords like 'account', 'a/c', 'acct', 'acc no'
    BANK_CONTEXT_KEYWORDS = (
        r'(?:account|acct|a/c|acc|bank|savings|current|khata|katha|passbook|'
        r'transfer|neft|rtgs|imps|deposit|branch|number)'
    )
    BANK_ACCOUNT_REGEX = re.compile(
        rf'(?:{BANK_CONTEXT_KEYWORDS})[\s\:\#\-no\.a-zA-Z]*?(\d{{9,18}})\b|'
        rf'\b(\d{{9,18}})[\s\:\#\-\.a-zA-Z]*?(?:{BANK_CONTEXT_KEYWORDS})\b',
        re.IGNORECASE
    )

    # Card Numbers (13-19 digits grouped in 4s or contiguous)
    CARD_REGEX = re.compile(
        r'\b(?:\d{4}[\s\-]?){3}\d{4}\b|'
        r'\b\d{15,16}\b'
    )

    # URLs and Social Media
    URL_REGEX = re.compile(
        r'https?://(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)|'
        r'\bwww\.[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&//=]*)|'
        r'\b(?:wa\.me|api\.whatsapp\.com|t\.me|telegram\.me|instagram\.com|facebook\.com|fb\.com|'
        r'bit\.ly|tinyurl\.com|youtube\.com|youtu\.be|x\.com|twitter\.com|linkedin\.com)/[-a-zA-Z0-9_.~#?&//=]+',
        re.IGNORECASE
    )

    # Address Detection: 6-digit Indian PIN codes + Address Keywords (Karnataka & Pan-India)
    PIN_CODE_REGEX = re.compile(
        r'(?:(?:\bpin|\bpincode|\bpostal\s*code|\bzip|\bpin\s*no)[\s\:\.\-]*([1-9][0-9]{5})\b)|'
        r'(?:\b(5[6-9][0-9]{4})\b)',  # Karnataka 6-digit PIN codes (560000 - 599999)
        re.IGNORECASE
    )

    ADDRESS_KEYWORDS = [
        'door no', 'house no', 'd.no', 'flat no', 'plot no', 'street',
        'cross', 'main road', 'layout', 'nagar', 'colony', 'post office',
        'taluk', 'hobli', 'district', 'village', 'grama', 'opp', 'opposite',
        'near temple', 'near school', 'near bustand', 'near bus stand'
    ]

    # Prohibited Platform Bypass and Fraud Keywords
    DEFAULT_PROHIBITED_KEYWORDS = [
        # Platform Bypass & Contact Offloading
        'call me on', 'call me at', 'contact me on', 'contact me directly',
        'whatsapp me', 'telegram me', 'ping me on whatsapp', 'message me on whatsapp',
        'connect outside', 'talk outside', 'bypass', 'direct deal', 'direct trade',
        'phone pe call', 'gpay pe send',
        # Payment Fraud & Advance Demands
        'advance payment', 'pay in advance', 'send advance', 'half payment first',
        'token amount first', 'transfer advance', 'pay upfront', 'send money first',
        'wire transfer', 'crypto', 'gift card', 'bitcoin',
        # Abuse & Harassment keywords
        'fraud', 'scam', 'cheat', 'fake farmer', 'fake produce'
    ]

    def __init__(self):
        # Cache active DB filter rules or fall back to defaults
        self._db_rules = None

    def _get_active_db_rules(self) -> List[FilterRule]:
        try:
            return list(FilterRule.objects.filter(is_active=True))
        except Exception:
            return []

    def _normalize_text(self, text: str) -> str:
        """Helper to lowercase and normalize multi-spaces."""
        return re.sub(r'\s+', ' ', text).strip()

    def _check_written_numbers(self, text: str) -> Optional[str]:
        """Detect phone numbers spelled out in words (English or Kannada phonetics)."""
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        digit_seq = []
        for word in words:
            if word in self.WORD_DIGITS:
                digit_seq.append(self.WORD_DIGITS[word])
            else:
                if len(digit_seq) >= 7:
                    return "".join(digit_seq)
                digit_seq = []
        if len(digit_seq) >= 7:
            return "".join(digit_seq)
        return None

    def _luhn_checksum(self, card_number: str) -> bool:
        """Verify credit/debit card numbers using the Luhn algorithm."""
        digits = [int(c) for c in re.sub(r'\D', '', card_number)]
        if len(digits) not in [13, 14, 15, 16, 19]:
            return False
        checksum = 0
        reverse_digits = digits[::-1]
        for i, d in enumerate(reverse_digits):
            if i % 2 == 1:
                doubled = d * 2
                checksum += (doubled - 9) if doubled > 9 else doubled
            else:
                checksum += d
        return checksum % 10 == 0

    def detect_phone_numbers(self, text: str) -> List[DetectedViolation]:
        violations = []
        # 1. Regex check - only matches numbers starting with 6-9
        for match in self.PHONE_REGEX.finditer(text):
            val = match.group()
            digits = re.sub(r'\D', '', val)
            if len(digits) >= 10:
                violations.append(DetectedViolation(
                    rule_type='phone',
                    rule_name='Phone Number Detected',
                    detected_text=val,
                    severity='high',
                    action='block',
                    start_idx=match.start(),
                    end_idx=match.end()
                ))

        # 2. Check using python-phonenumbers for standard formats (+91 etc.)
        # Only accept numbers starting with 6-9 (valid Indian mobile prefixes)
        try:
            for match in phonenumbers.PhoneNumberMatcher(text, "IN"):
                val = match.raw_string
                digits = re.sub(r'\D', '', val)
                # Only flag if it starts with valid Indian mobile prefix (6-9)
                if digits and digits[0] in '6789':
                    # Avoid duplicate if already covered
                    if not any(v.detected_text == val or val in v.detected_text for v in violations):
                        violations.append(DetectedViolation(
                            rule_type='phone',
                            rule_name='Phonenumbers Library Match',
                            detected_text=val,
                            severity='high',
                            action='block',
                            start_idx=match.start,
                            end_idx=match.end
                        ))
        except Exception:
            pass

        # 3. Check written numbers
        written = self._check_written_numbers(text)
        if written and len(written) >= 10:
            violations.append(DetectedViolation(
                rule_type='phone',
                rule_name='Spelled-out Phone Number Detected',
                detected_text=f"Spelled out digits: {written}",
                severity='high',
                action='block'
            ))

        return violations

    def detect_emails(self, text: str) -> List[DetectedViolation]:
        violations = []
        # Standard email
        for match in self.EMAIL_REGEX.finditer(text):
            violations.append(DetectedViolation(
                rule_type='email',
                rule_name='Email Address Detected',
                detected_text=match.group(),
                severity='high',
                action='warn',
                start_idx=match.start(),
                end_idx=match.end()
            ))

        # Obfuscated email
        for match in self.OBFUSCATED_EMAIL_REGEX.finditer(text):
            val = match.group()
            if not any(val in v.detected_text for v in violations):
                violations.append(DetectedViolation(
                    rule_type='email',
                    rule_name='Obfuscated Email Detected',
                    detected_text=val,
                    severity='high',
                    action='warn',
                    start_idx=match.start(),
                    end_idx=match.end()
                ))

        return violations

    def detect_upi_ids(self, text: str) -> List[DetectedViolation]:
        violations = []
        # Standard VPA
        for match in self.UPI_REGEX.finditer(text):
            violations.append(DetectedViolation(
                rule_type='upi',
                rule_name='UPI / VPA ID Detected',
                detected_text=match.group(),
                severity='critical',
                action='block',
                start_idx=match.start(),
                end_idx=match.end()
            ))

        # Obfuscated UPI
        for match in self.OBFUSCATED_UPI_REGEX.finditer(text):
            val = match.group()
            if not any(val in v.detected_text for v in violations):
                violations.append(DetectedViolation(
                    rule_type='upi',
                    rule_name='Obfuscated UPI Detected',
                    detected_text=val,
                    severity='critical',
                    action='block',
                    start_idx=match.start(),
                    end_idx=match.end()
                ))

        return violations

    def detect_bank_details(self, text: str) -> List[DetectedViolation]:
        violations = []
        # 1. IFSC code
        for match in self.IFSC_REGEX.finditer(text):
            violations.append(DetectedViolation(
                rule_type='bank',
                rule_name='Bank IFSC Code Detected',
                detected_text=match.group(),
                severity='critical',
                action='block',
                start_idx=match.start(),
                end_idx=match.end()
            ))

        # 2. Bank Account Numbers with context
        for match in self.BANK_ACCOUNT_REGEX.finditer(text):
            violations.append(DetectedViolation(
                rule_type='bank',
                rule_name='Bank Account Number Detected',
                detected_text=match.group(),
                severity='critical',
                action='block',
                start_idx=match.start(),
                end_idx=match.end()
            ))

        # 3. Card numbers with Luhn check
        for match in self.CARD_REGEX.finditer(text):
            val = match.group()
            if self._luhn_checksum(val):
                violations.append(DetectedViolation(
                    rule_type='bank',
                    rule_name='Payment Card Number Detected',
                    detected_text=val,
                    severity='critical',
                    action='block',
                    start_idx=match.start(),
                    end_idx=match.end()
                ))

        return violations

    def detect_urls(self, text: str) -> List[DetectedViolation]:
        violations = []
        for match in self.URL_REGEX.finditer(text):
            violations.append(DetectedViolation(
                rule_type='url',
                rule_name='URL / Social Link Detected',
                detected_text=match.group(),
                severity='medium',
                action='block',
                start_idx=match.start(),
                end_idx=match.end()
            ))
        return violations

    def detect_addresses(self, text: str) -> List[DetectedViolation]:
        violations = []
        # Check PIN codes
        for match in self.PIN_CODE_REGEX.finditer(text):
            violations.append(DetectedViolation(
                rule_type='address',
                rule_name='Postal PIN Code Detected',
                detected_text=match.group(),
                severity='medium',
                action='warn',
                start_idx=match.start(),
                end_idx=match.end()
            ))

        # Check address keyword clusters (2+ address keywords in close proximity)
        lower_text = text.lower()
        matched_kw = [kw for kw in self.ADDRESS_KEYWORDS if kw in lower_text]
        if len(matched_kw) >= 2:
            violations.append(DetectedViolation(
                rule_type='address',
                rule_name='Physical Address Pattern Detected',
                detected_text=", ".join(matched_kw),
                severity='medium',
                action='warn'
            ))

        return violations

    def detect_keywords(self, text: str) -> List[DetectedViolation]:
        violations = []
        lower_text = text.lower()

        # Check default prohibited keywords
        for kw in self.DEFAULT_PROHIBITED_KEYWORDS:
            if re.search(r'\b' + re.escape(kw) + r'\b', lower_text, re.IGNORECASE):
                violations.append(DetectedViolation(
                    rule_type='keyword',
                    rule_name=f"Prohibited Keyword: '{kw}'",
                    detected_text=kw,
                    severity='high',
                    action='block'
                ))

        # Check custom DB filter rules
        db_rules = self._get_active_db_rules()
        for rule in db_rules:
            if not rule.pattern or not rule.pattern.strip():
                # Skip rules with empty pattern (auto-created rules that would match everything)
                continue
            try:
                pattern = re.compile(rule.pattern, re.IGNORECASE)
                match = pattern.search(text)
                if match:
                    violations.append(DetectedViolation(
                        rule_type=rule.rule_type,
                        rule_name=rule.name,
                        detected_text=match.group(),
                        severity=rule.severity,
                        action=rule.action,
                        start_idx=match.start(),
                        end_idx=match.end()
                    ))
            except Exception:
                continue

        return violations

    def redact_text(self, text: str, violations: List[DetectedViolation]) -> str:
        """
        Replace detected sensitive entities in the message with placeholder tags.
        e.g. [PHONE REDACTED], [UPI REDACTED], [EMAIL REDACTED], [LINK REDACTED]
        """
        redacted = text
        # Redact specific detected substrings
        for v in violations:
            if v.detected_text and v.detected_text in redacted:
                tag = f"[{v.rule_type.upper()} REDACTED]"
                redacted = redacted.replace(v.detected_text, tag)

        # Fallback regex replacements to ensure no leaks
        redacted = self.PHONE_REGEX.sub('[PHONE REDACTED]', redacted)
        redacted = self.EMAIL_REGEX.sub('[EMAIL REDACTED]', redacted)
        redacted = self.UPI_REGEX.sub('[UPI REDACTED]', redacted)
        redacted = self.IFSC_REGEX.sub('[IFSC REDACTED]', redacted)
        redacted = self.URL_REGEX.sub('[LINK REDACTED]', redacted)

        return redacted

    def filter_message(self, content: str) -> FilterResult:
        """
        Main entry point for filtering a chat message.
        Runs all detector modules, aggregates violations, determines blocking action,
        and provides redacted content.
        """
        if not content or not content.strip():
            return FilterResult(is_clean=True, original_content=content, filtered_content=content)

        all_violations: List[DetectedViolation] = []

        # Run all detection modules
        all_violations.extend(self.detect_phone_numbers(content))
        all_violations.extend(self.detect_emails(content))
        all_violations.extend(self.detect_upi_ids(content))
        all_violations.extend(self.detect_bank_details(content))
        all_violations.extend(self.detect_urls(content))
        all_violations.extend(self.detect_addresses(content))
        all_violations.extend(self.detect_keywords(content))

        # Deduplicate violations by rule_type and detected_text
        unique_violations: List[DetectedViolation] = []
        seen = set()
        for v in all_violations:
            key = (v.rule_type, v.detected_text.strip().lower())
            if key not in seen:
                seen.add(key)
                unique_violations.append(v)

        is_clean = len(unique_violations) == 0
        should_block = any(v.action == 'block' for v in unique_violations)
        should_warn = any(v.action == 'warn' for v in unique_violations)
        filter_types = list(set(v.rule_type for v in unique_violations))

        filtered_content = content if is_clean else self.redact_text(content, unique_violations)

        return FilterResult(
            is_clean=is_clean,
            violations=unique_violations,
            filtered_content=filtered_content,
            original_content=content,
            should_block=should_block,
            should_warn=should_warn,
            filter_types=filter_types
        )


# Global singleton instance
message_filter_engine = MessageFilteringEngine()
