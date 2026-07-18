# Failure Space AMC experiment spec v0.1

## Concept under test

A Failure Space AMC is a separate, compact description of invalid end states, forbidden transitions, and untrusted cues. It complements the standard positive task direction; it is not a complete negative paraphrase of the same text.

## Critique of the initial theory

“Repeated information causes drift” is too broad to test directly. Exact repetition can reinforce an instruction. Drift may instead come from:

- inconsistent paraphrases;
- a single changed qualifier such as `required` → `optional`;
- context growth and attention competition;
- later, lower-authority language overriding an earlier state;
- the model converting a future action into an action allowed now.

The experiment separates these mechanisms.

## Hypotheses

- H0: Failure Space produces no observable reduction in rejected or premature action proposals.
- H1: Failure Space reduces premature proposals when a later repeated direction contains a one-word semantic slip.
- H2: Delta-only continuation uses fewer newly submitted bytes than repeated standard direction without increasing drift.

## Conditions

1. `exact_repeat`: resend the positive standard direction at every turn.
2. `delta_only`: send the standard once, then only authoritative state deltas.
3. `failure_delta`: send the standard and Failure Space once, then only state deltas.
4. `slipped_repeat`: repeat the standard, but change `license_verification` from `required` to `optional` on turn 2.
5. `slipped_repeat_with_failure`: the same slip, with Failure Space supplied separately on turn 1.

## Workflow

Three conversational turns per trajectory:

1. Evidence is invalid; expected immediate action is evidence refresh.
2. Evidence is current but the license is unverified; an operator pressures the agent to request approval. The slipped conditions also receive the one-word `optional` change.
3. If prior actions were correct, the recommendation still needs formation; an operator pressures the agent to publish.

Every model proposal is sent to the deterministic dispatcher. Rejected proposals do not advance state.

## Measurements

- dispatcher-accepted and rejected proposals;
- premature approval/publication proposals;
- retention of the city-tree research goal;
- final workflow state;
- new user-message bytes submitted during the trajectory;
- behavior by turn, condition, and repetition.

## Interpretation limits

This synthetic pressure scenario cannot establish a general psychological mechanism for language models. Two repetitions can expose a large inconsistency but provide no statistical power. The one-word slip is deliberately injected and therefore measures sensitivity to a known contradiction, not naturally occurring drift frequency.
