"""Reconstructed Classical Attic (c. 400 BC) pronunciation, transcribed to IPA.

Follows the reconstruction in W. Sidney Allen, *Vox Graeca* (3rd ed., 1987) -
the standard scholarly account of how educated Athenians of the late 5th /
4th century BC actually sounded. The salient features that distinguish this
from later Koine / Erasmian / Modern Greek values:

  * Vowel LENGTH is phonemic: ε/ο are short close-mid [e]/[o]; η/ω are long
    open-mid [ɛː]/[ɔː]; α ι υ are short or long. υ is front-rounded [y(ː)].
  * The "spurious diphthongs": ει = long close [eː] (NOT [ei̯]) and ου =
    long close [uː] (NOT [ou̯]) throughout. ει is the one exception: in
    hiatus (immediately followed by another vowel in the same word) it
    keeps an audible offglide instead of reducing to a pure long
    monophthong (Allen p.79; e.g. βασιλεία -> ...leia, not ...leːa; see
    _SPURIOUS_HIATUS_GLIDE). ου does NOT get the same hiatus exception -
    it stays [uː] regardless of what follows.
  * In hiatus, the genuine diphthongs αι/αυ/ευ/οι/υι - and ει, once it's
    already diphthongal there - don't just keep a plain offglide, the
    offglide itself is LENGTHENED/geminated: Allen, Vox Graeca pp.84-85,
    "[ayy], [aww], [oyy], [eww], [üyy]" (English parallels "high yield,
    bow-wave, toy yacht") for αι/αυ/οι/ευ/υι, and ει before a vowel
    likewise stands for [eyy] (not the single-glide [ei̯] a naive reading
    of the spurious-diphthong exception above would suggest). ου is not on
    this list at all - it never gets a hiatus-lengthened glide because it
    never gets a glide back in the first place.
  * οι is front-rounded [œi̯] ("as in French feuille"), not back-rounded
    [oi̯] - Allen pp.84-85: direct phonetic evidence is lacking, but he
    finds a back [oi̯] hard to reconcile with Thucydides' report (2.54) of
    genuine confusion over whether an oracle had said λοιμός "plague" or
    λιμός "famine", which is only readily explained if οι was already
    close to ι in frontness. This does NOT extend to ῳ (ω + iota
    subscript), which stays back [ɔːi̯] - Allen's argument is specific to
    οι and nothing in the source extends it to the long-vowel-plus-iota
    diphthongs.
  * φ θ χ are aspirated STOPS [pʰ tʰ kʰ], not the fricatives of later Greek.
  * ζ = [zd]; ξ = [ks]; ψ = [ps].
  * γ before a velar (γ κ χ ξ) or before μ is the nasal [ŋ] ("gamma nasal"),
    e.g. ἄγγελος [áŋɡelos], πρᾶγμα [prâːɡma].
  * Rough breathing = [h]; initial ῥ = voiceless [r̥]; and in a geminate ῥῥ/ρρ
    (e.g. Πυρρός, ἄρρην) the second element is likewise voiceless [r̥],
    matching the orthographic convention of marking it with rough breathing.
  * A pitch (melodic) accent, not a stress accent. On a long vowel or
    diphthong (two morae), acute and circumflex put high and low tone on
    DIFFERENT morae - not a flat tone confined to one of them:
      - Acute is voiced low-then-high: low on the first mora, high on the
        second (e.g. ῥήτωρ's η -> ɛːˊ, not ɛ́ː; a diphthong like οὐ -> uːˊ).
      - Circumflex is voiced high-then-low: it goes IN high on the first
        mora, then drops on the second (e.g. μοῖρα's οι -> ο gets the
        acute, ι gets the grave - it doesn't rise into the accented
        syllable, it starts there).
    On a short (monomoraic) vowel there's only one mora, so both simply
    collapse to a plain high tone. We mark the accented mora(e) with plain
    IPA high (´) and low (`) tone diacritics rather than a stress mark ˈ
    or a single contour symbol - this mirrors how the accent marks
    themselves work (circumflex is traditionally analyzed as a fusion of
    acute + grave over two morae of one long syllable).

Length caveat: for the "dichrona" α ι υ, ordinary spelling does not show
length - this module transcribes one long only when the string it's given
actually carries a macron (ᾱ ῑ ῡ / combining U+0304); otherwise it defaults
to short. The caller is what supplies that information: LSJ records true
length for roughly 30% of headwords in the `orth_orig` attribute of its own
`<head>` element (a hyphenated form meant for the print edition's
line-wrapping, e.g. `<head orth_orig="τῑμ-ή">τιμή</head>`) - see
`merge_lsj_vowel_length` in scripts/build_unabridged_xml.py, which recovers
those marks and grafts them onto the headword actually displayed before
calling greek_to_ipa() on it. Where LSJ doesn't record a length (the
remaining ~70%), this module still can't do anything but default to short -
that's the source data's limitation, not this module's.
"""
import unicodedata

# Combining diacritics (all work is done on NFD-decomposed text).
SMOOTH = '̓'      # psili       ᾿  (no sound)
ROUGH = '̔'       # dasia        ῾  -> [h]
ACUTE = '́'       # oxia         ´  -> high tone
GRAVE = '̀'       # varia        `  -> contextual low (rendered plain)
CIRCUMFLEX = '͂'  # perispomeni  ῀  -> high-falling tone
IOTA_SUB = 'ͅ'    # ypogegrammeni ᾳ -> long diphthong offglide [i̯]
MACRON = '̄'      # -> long
BREVE = '̆'       # -> short
DIAERESIS = '̈'   # -> breaks a diphthong

_ACCENTS = {ACUTE, GRAVE, CIRCUMFLEX}
_DIACRITICS = {SMOOTH, ROUGH, ACUTE, GRAVE, CIRCUMFLEX, IOTA_SUB, MACRON, BREVE, DIAERESIS}

# IPA tone diacritics placed on the accented nucleus vowel.
TONE_HIGH = '́'  # combining acute -> high
TONE_LOW = '̀'   # combining grave -> low

VOWELS = set('αεηιουωΑΕΗΙΟΥΩ')

# Base monophthong values. (short_ipa, long_ipa, always_long?)
_MONO = {
    'α': ('a', 'aː', False),
    'ε': ('e', 'e', True),    # always short
    'η': ('ɛː', 'ɛː', True),  # always long
    'ι': ('i', 'iː', False),
    'ο': ('o', 'o', True),    # always short
    'υ': ('y', 'yː', False),
    'ω': ('ɔː', 'ɔː', True),  # always long
}

# Genuine diphthongs (first vowel + ι/υ offglide). ει and ου are the
# "spurious diphthongs" - long monophthongs by classical Attic. Only ει gets
# an exception in hiatus (immediately followed by another vowel within the
# same word), keeping an audible offglide instead of reducing to a pure
# long monophthong (Allen, Vox Graeca p.79; e.g. βασιλεία -> ...leia, not
# ...leːa) - ου stays [uː] in every context, hiatus included.
# _SPURIOUS_HIATUS_GLIDE below overrides ει specifically when that
# following-vowel condition holds, with an already-lengthened glide (see
# _HIATUS_GLIDE_LENGTHENERS just below) since Allen treats ει-in-hiatus as
# following the same lengthening pattern as the genuine diphthongs, not as
# merely regaining a plain single glide.
# οι is front-rounded [œi̯] ("as in French feuille"), not back [oi̯] - see
# module docstring for Allen's Thucydides-based argument for this.
_DIPHTHONGS = {
    'αι': 'ai̯', 'αυ': 'au̯',
    'ει': 'eː', 'ευ': 'eu̯',
    'οι': 'œi̯', 'ου': 'uː',
    'υι': 'yi̯',
    'ηυ': 'ɛːu̯', 'ωυ': 'ɔːu̯',
}
_SPURIOUS_HIATUS_GLIDE = {'ει': 'ei̯ː'}

# In hiatus, a genuine diphthong's offglide is lengthened/geminated rather
# than staying a plain single glide - Allen, Vox Graeca pp.84-85: "[ayy],
# [aww], [oyy], [eww], [üyy]" for αι/αυ/οι/ευ/υι (English parallels "high
# yield, bow-wave, toy yacht"). ηυ/ωυ aren't in Allen's list (both are
# vanishingly rare to begin with) and are left unaffected; ου isn't a
# genuine diphthong to begin with, so it's out of scope here regardless.
_HIATUS_GLIDE_LENGTHENERS = {'αι', 'αυ', 'ευ', 'οι', 'υι'}

def _lengthen_offglide(ipa_diphthong):
    for glide in _GLIDE_OFFSETS:
        if ipa_diphthong.endswith(glide):
            return ipa_diphthong + 'ː'
    return ipa_diphthong

# Long diphthongs written with iota subscript.
_IOTA_SUB_DIPH = {'α': 'aːi̯', 'η': 'ɛːi̯', 'ω': 'ɔːi̯'}

_CONS = {
    'β': 'b', 'γ': 'ɡ', 'δ': 'd',
    'π': 'p', 'τ': 't', 'κ': 'k',
    'φ': 'pʰ', 'θ': 'tʰ', 'χ': 'kʰ',
    'ζ': 'zd', 'ξ': 'ks', 'ψ': 'ps',
    'λ': 'l', 'μ': 'm', 'ν': 'n', 'ρ': 'r',
    'σ': 's', 'ς': 's',
}

# γ assimilates to the velar nasal [ŋ] before another velar stop (κ γ χ) or
# before ξ - and also before μ (the -γμ- cluster, e.g. πρᾶγμα, δόγμα).
_GAMMA_NASALIZERS = set('γκχξμ')
_VOICED_AFTER_S = set('βγδμ')  # σ before one of these -> [z]


def _decompose(token):
    """NFD-decomposes and regroups into (base_lower, set_of_marks) units,
    preserving order. Non-letter characters come through as (char, empty set)."""
    units = []
    for ch in unicodedata.normalize('NFD', token):
        if ch in _DIACRITICS and units:
            units[-1][1].add(ch)
        else:
            units.append([ch.lower(), set()])
    return units


_GLIDE_OFFSETS = ('i̯', 'u̯')

def _split_moras(ipa_vowel):
    """Splits a bimoraic nucleus (long vowel or diphthong) into
    (first_mora, second_mora) at its natural boundary - the offglide for a
    diphthong (ai̯ -> a | i̯), or the length mark for a plain long monophthong
    (ɛː -> ɛ | ː). A monomoraic (short, single-character) nucleus has only
    one mora to place a tone on, so it's returned as (whole, whole) and the
    caller treats that as "no real split". Searches for the glide rather
    than requiring it at the very end, since a hiatus-lengthened offglide
    (see _lengthen_offglide) has a trailing ː after it (ai̯ː -> a | i̯ː) that
    an endswith check on the glide alone would miss."""
    for glide in _GLIDE_OFFSETS:
        idx = ipa_vowel.find(glide)
        if idx > 0:
            return ipa_vowel[:idx], ipa_vowel[idx:]
    if ipa_vowel.endswith('ː') and len(ipa_vowel) > 1:
        return ipa_vowel[:-1], 'ː'
    return ipa_vowel, ipa_vowel

def _apply_tone(ipa_vowel, marks):
    """Adds IPA tone diacritics reflecting the Greek pitch accent carried in
    `marks`, using the plain high (´) and low (`) tone marks rather than a
    contour diacritic - on a bimoraic nucleus (long vowel/diphthong) the two
    marks land on different morae, mirroring how the accent is actually
    voiced:
      - Acute is voiced low-then-high: the FIRST mora is low (left
        unmarked), the SECOND is high (e.g. ῥήτωρ's η -> ɛːˊ, not ɛ́ː).
      - Circumflex is voiced high-then-low: it goes IN high on the FIRST
        mora, then drops on the SECOND (e.g. μοῖρα's οι -> ο get the acute,
        ι gets the grave: oˊi̯ˋ) - not a rise into the accented syllable.
    On a monomoraic (short) vowel there's only one mora, so both simply
    collapse to a plain high tone on that single mora."""
    if not ipa_vowel:
        return ipa_vowel
    if not (CIRCUMFLEX in marks or ACUTE in marks):
        return ipa_vowel  # GRAVE: rendered plain (its high tone is contextually suppressed)

    first_mora, second_mora = _split_moras(ipa_vowel)
    monomoraic = second_mora is ipa_vowel or second_mora == ipa_vowel
    if monomoraic:
        return ipa_vowel[0] + TONE_HIGH + ipa_vowel[1:]

    if CIRCUMFLEX in marks:
        return (first_mora[0] + TONE_HIGH + first_mora[1:]
                + second_mora[0] + TONE_LOW + second_mora[1:])
    return first_mora + second_mora[0] + TONE_HIGH + second_mora[1:]  # ACUTE


def _transcribe_units(units):
    out = []
    n = len(units)
    i = 0
    word_start = True
    while i < n:
        base, marks = units[i]
        nxt = units[i + 1] if i + 1 < n else None

        if base in VOWELS:
            base = base  # already lowercased
            # Rough breathing on a word-initial vowel/diphthong -> leading [h].
            if word_start and ROUGH in marks:
                out.append('h')

            # Try a two-vowel diphthong: current + ι/υ offglide, unless the
            # offglide carries a diaeresis (which forces separate syllables).
            combined = None
            if (nxt and nxt[0] in ('ι', 'υ') and DIAERESIS not in nxt[1]
                    and base + nxt[0] in _DIPHTHONGS):
                digraph = base + nxt[0]
                combined = _DIPHTHONGS[digraph]
                after = units[i + 2] if i + 2 < n else None
                hiatus = after and after[0] in VOWELS
                if hiatus and digraph in _SPURIOUS_HIATUS_GLIDE:
                    combined = _SPURIOUS_HIATUS_GLIDE[digraph]
                elif hiatus and digraph in _HIATUS_GLIDE_LENGTHENERS:
                    combined = _lengthen_offglide(combined)
                # Accent may be written on either element; take marks from both.
                pair_marks = marks | nxt[1]
                out.append(_apply_tone(combined, pair_marks))
                i += 2
                word_start = False
                continue

            # Iota-subscript long diphthong (ᾳ ῃ ῳ).
            if IOTA_SUB in marks and base in _IOTA_SUB_DIPH:
                out.append(_apply_tone(_IOTA_SUB_DIPH[base], marks))
                i += 1
                word_start = False
                continue

            # Plain monophthong. A circumflex can only sit on a long nucleus,
            # so it (like an explicit macron) forces length on a dichronon.
            short_ipa, long_ipa, always_long = _MONO[base]
            if always_long or MACRON in marks or CIRCUMFLEX in marks:
                ipa = long_ipa
            else:
                ipa = short_ipa  # dichrona default short (see module docstring)
            out.append(_apply_tone(ipa, marks))
            i += 1
            word_start = False
            continue

        if base in _CONS:
            prev_base = units[i - 1][0] if i > 0 else None
            if base == 'γ' and nxt and nxt[0] in _GAMMA_NASALIZERS:
                out.append('ŋ')
            elif base in ('σ', 'ς') and nxt and nxt[0] in _VOICED_AFTER_S:
                out.append('z')  # σ voices before β γ δ μ
            elif base == 'ρ' and (word_start or prev_base == 'ρ'):
                # ῥ (rough breathing, word-initial) and the second element of
                # a geminate ρρ (e.g. Πυρρός, ἄρρην) are both voiceless [r̥].
                out.append('r̥')
            else:
                out.append(_CONS[base])
            i += 1
            word_start = False
            continue

        # Anything else (spaces, punctuation, stray Latin) passes through and
        # resets the word-start state so a following vowel re-checks breathing.
        out.append(units[i][0])
        word_start = True
        i += 1

    return ''.join(out)


def greek_to_ipa(word):
    """Transcribes a Greek headword to a reconstructed-Attic IPA string
    (bracketed). Returns '' if the input has no Greek letters at all, so
    callers can skip non-Greek/numeric lemmas. Multi-word lemmas and hyphen/
    space-separated parts are transcribed piece by piece."""
    if not word or not any(unicodedata.normalize('NFD', c)[0] in VOWELS
                           or c.lower() in _CONS for c in word):
        return ''
    units = _decompose(word.strip())
    ipa = _transcribe_units(units)
    ipa = ipa.strip()
    if not ipa:
        return ''
    return f'[{ipa}]'


if __name__ == '__main__':
    # Quick self-check against textbook Vox Graeca values.
    samples = [
        'λόγος', 'ἄνθρωπος', 'ῥήτωρ', 'οἶκος', 'εἰμί', 'Ζεύς', 'ἵππος',
        'ἀγαθός', 'σῶμα', 'γλῶσσα', 'ἄγγελος', 'πρᾶγμα', 'ἐγκέφαλος',
        'φιλοσοφία', 'θεός', 'χείρ', 'ψυχή', 'ξένος', 'βασιλεύς', 'μῆνις',
        'τῇ', 'ᾠδή', 'υἱός', 'αὐτός', 'εὖ', 'δόγμα', 'Πυρρός', 'ἄρρην',
        'μοῖρα', 'βασιλεία', 'ὑγιεία',
    ]
    for w in samples:
        print(f'{w:14s} {greek_to_ipa(w)}')
