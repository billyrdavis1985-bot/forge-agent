# Feedback-Loop Principle (design note — NOT built)

Council recommendation #6. This is a **guardrail written down before it is
needed**, not implemented code. It governs what happens *if and when* Forge's
findings are ever used to improve the critics it measures.

## The trap this prevents

Forge measures critics. The tempting next step is to feed what it finds back
into training them. This looks like a virtuous loop. It is a trap.

If the **same system** discovers a weakness, generates the fix, and certifies
the fix, you train the critic to pass *your specific tests* rather than to
reason better. The measured metric improves while general capability does not —
exactly the proxy-inflation phenomenon this research program exists to expose,
recreated one level up. An adaptive-overfitting machine.

## The rule

> Forge may help find a weakness and may help fix it.
> Forge may not declare its own fix successful.

## The three-chamber separation

**Discovery** — Forge identifies weaknesses; may generate *candidate*
corruptions. Everything Forge currently does lives here.

**Training** — those candidates become curriculum. The critic trains on them.

**Certification** — different rules. A **frozen, sealed holdout** the training
process has never seen and cannot access: versioned and sealed *before* training,
drawn from disjoint problems, ideally including naturally-occurring reasoning
errors (not only synthetic corruptions from the same generator). The system that
found the weakness cannot certify its own repair.

## Why documented and not built

Retraining from Forge's findings is not current work; the training pipeline is
not yet fixed; current scale does not need the full machinery. The *principle*
must not be lost; the *architecture* is best designed against a real workflow.

## Open strategic question (deliberately unresolved)

Does the feedback loop belong in Forge at all? Forge's strongest identity may be
as a *measurement instrument* that feeds a separate training pipeline — in which
case Discovery is Forge, and Training/Certification live elsewhere. Resolve when
retraining becomes real.
