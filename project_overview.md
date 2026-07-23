# Verified Financial Research Agent

A build plan, written to be followed in order.

---

## 1. Problem Statement

Large language models are good at reasoning and bad at remembering exact numbers. Ask a model what Datadog reported for cost of revenue in a specific quarter and it will produce a confident, well formatted, plausible number. Sometimes that number is right. Often it is not. There is no way to tell which from looking at the output.

This is the single biggest reason language models are not trusted for financial analysis. The reasoning is usually fine. The facts underneath it are unverifiable.

**The problem this project solves:** produce financial analysis where every single number can be traced back to a specific value in a specific SEC filing, and where that trace is checked by code rather than promised by the model.

**The approach:** the model is never allowed to supply a number from memory. It may only report numbers that arrived from a real SEC data fetch during this run. Before any output reaches the user, a verification pass confirms that every figure cited actually exists in the data that was fetched. Anything that fails the check is removed and reported as unverified.

**Why an agent and not a script:** the sequence of steps is not knowable in advance. A question about one company for two quarters takes four tool calls. A question comparing two companies with different fiscal year ends across six quarters takes thirty, and requires noticing the calendar mismatch partway through. The model decides what to do next based on what the previous step returned. That is the definition of an agent, and it is why this cannot be written as a fixed pipeline.

---

## 2. What This Is and What It Is Not

**It is:** a small, honest agent with a hard verification layer and a measured error rate.

**It is not:** a chatbot for finance, a stock picker, or a multi agent framework demonstration.

The deliverable that matters is not the architecture. It is a number: the citation hallucination rate before verification was added, and the rate after. Everything in this plan exists to produce that number honestly.

---

## 3. The Core Idea, In Plain Terms

An agent is a loop. That is genuinely all it is.

1. You send the model a goal and a list of tools it is allowed to use.
2. The model replies with either a tool it wants to use, or a final answer.
3. If it asked for a tool, your code runs that tool and sends the result back.
4. Go to step 2.
5. Stop when the model gives a final answer, or when you hit an iteration cap.

The intelligence is entirely in the model. The loop is dumb Python that does what it is told. Your job as the engineer is to decide what tools exist, what the model is allowed to do with them, and what gets checked before the output is trusted.

---

## 4. Tech Stack

Deliberately small.

| Piece | Choice | Why |
| --- | --- | --- |
| Language | Python 3.11+ | Nothing exotic needed |
| Model | Claude or GPT via SDK | Direct API calls, no framework until v4 |
| Data source | SEC EDGAR `companyfacts` API | Free, no key, returns structured JSON |
| Storage | JSON files, then SQLite at v3 | Do not overbuild this |
| Framework | None until v4, then LangGraph | The point is to build it before abstracting it |

**The key technical fact that makes this project feasible:**

```
https://data.sec.gov/api/xbrl/companyfacts/CIK0001561550.json
```

One HTTP GET. No API key. It returns every financial concept a company has ever reported to the SEC, already structured, already tagged by fiscal period and by the filing it came from. No PDF parsing, no HTML scraping, no table extraction.

SEC requires a User-Agent header identifying you, for example `Vedant Vardhaan vedant@example.com`. Requests are limited to ten per second, which you will never approach.

---

## 5. The Versions

Five versions. Each one runs end to end and does something useful. If you stop at any point, you have a working project rather than an unfinished one.

---

### v0 — The Raw Loop

**Goal:** watch an agent make a decision you did not script.

**Time:** one weekend.

**Components:**

- `get_company_facts(ticker)` — resolves ticker to CIK, fetches the JSON, returns a trimmed version containing only the concepts likely to be relevant. The raw file can be several megabytes, so filter before it reaches the model.
- `calculate(expression)` — evaluates a arithmetic string and returns the result. The model must never do arithmetic itself.
- `done(answer)` — the model calls this to end the run.
- The loop — roughly forty lines. Call model, read tool request, execute, append result, repeat. Cap at fifteen iterations.
- Trajectory printing — print every tool call and result to the terminal as it happens.

**Definition of done:** you type a question about one company, and you watch it fetch, then compute a different number of times depending on the question, then answer.

**What you learn:** what an agent actually is. Tool schemas, the message accumulation pattern, why iteration caps exist, what a malformed tool call looks like.

**What is deliberately missing:** verification, evaluation, memory, multiple companies, any framework.

---

### v1 — Citations and Verification

**Goal:** stop the model being able to invent a number.

**Time:** three to four days.

**Components:**

- **Structured output.** The agent returns a data structure, not a formatted string. Every figure is an object containing the value, the XBRL concept name, the fiscal period, and the accession number of the filing it came from.
- **The verification pass.** Before anything is printed, code walks the structured output and confirms each figure exists in the JSON that was actually fetched this run. Same concept, same period, same value.
- **Failure handling.** A figure that fails verification is not printed. It is moved to an unverified list.
- **The "could not determine" section.** The agent is required to state what it was unable to answer from the data available. This is not cosmetic. An analyst who never says "I do not know" is not trustworthy.
- **Prompt work.** The system prompt now states that numbers may only come from tool results, and that every reported figure must carry its concept and period.

**Definition of done:** you can deliberately prompt it toward a figure that is not in XBRL, and the verification layer catches the invention rather than printing it.

**What you learn:** the difference between asking a model to behave and enforcing behaviour in code. This is the single most important lesson in the project and the thing that separates it from a wrapper.

---

### v2 — The Evaluation Set

**Goal:** turn "it seems to work" into a number.

**Time:** four to five days. Most of it is hand verification, not coding.

**Components:**

- **Twenty to thirty ground truth questions.** You write them, and you verify the correct answers yourself by reading the filings. Mix of difficulties: single value lookups, single company trends, ratio calculations, and a few questions that are deliberately unanswerable from XBRL alone so you can test whether it admits that.
- **Three scoring dimensions, measured separately.**
  - *Numerical accuracy:* is the value correct, within a tolerance you define.
  - *Citation validity:* does the cited concept and period actually contain that value. This is checkable by code.
  - *Appropriate refusal:* on unanswerable questions, did it say so rather than guess.
- **The runner.** Executes all questions against a given version, writes results to a file, prints a summary table.
- **The comparison.** Run the suite against v0 and against v1. The difference is your headline metric.

**Definition of done:** you can state a sentence of this form with real numbers behind it: "Citation hallucination rate was X percent before programmatic verification and Y percent after."

**What you learn:** how agents are actually evaluated in industry. Why trajectory evaluation differs from final answer evaluation. Why LLM as judge is unreliable for numerical claims and why programmatic checking is better wherever it is possible.

**This is the minimum version worth putting on a resume.** It is the first one with a measurement attached.

---

### v3 — Multiple Companies and Memory

**Goal:** longer trajectories, and the problems that only appear when trajectories get long.

**Time:** one week. Timebox this strictly, it is where scope creep kills projects.

**Components:**

- **Comparison questions.** Two companies, same metric, aligned periods.
- **Fiscal calendar alignment.** Snowflake ends its fiscal year in January. Datadog ends in December. Comparing them naively produces wrong answers that look right. The agent has to notice and handle this.
- **A notes tool.** The agent writes intermediate findings to a scratchpad so it does not have to hold every fetched value in context.
- **Context compaction.** When the message history grows past a threshold, summarize the earlier portion and continue. Measure whether accuracy degrades as trajectories lengthen.
- **SQLite for run history.** Store every run, its trajectory, and its results, so you can look back at failures.

**Definition of done:** a two company comparison completes correctly with thirty plus tool calls, and you have data showing how accuracy changes as trajectory length grows.

**What you learn:** context management, which is the hardest practical problem in agent engineering and the one most candidates have opinions about rather than measurements.

---

### v4 — The LangGraph Rebuild

**Goal:** turn LangGraph from a tool you used into a tool you can critique.

**Time:** four to five days.

**Components:**

- The same agent, rebuilt as a LangGraph state machine.
- **Checkpointing.** Persist state so a failed run resumes rather than restarting.
- **Interrupts.** Pause for human approval at a chosen point.
- **Retry and error edges.** Handle tool failures as graph transitions rather than try blocks.
- **The comparison writeup.** What the framework gave you, what it cost you in control and clarity, and when you would choose each.

**Definition of done:** the eval suite runs against the LangGraph version and produces comparable scores, and you have a written comparison of the two implementations.

**What you learn:** what frameworks abstract, which you can only appreciate having written the raw version first. This directly upgrades how you can talk about the PwC work.

---

### v5 — Voice, Optional

**Goal:** a demo hook. One evening, after everything else.

**Components:**

- Speech to text on input, either Whisper locally or an API call. Wispr Flow at the OS level requires no code at all.
- Text to speech on output.
- **A second rendering of the results.** This is the part with actual engineering value. XBRL concept names and accession numbers are unlistenable aloud. Voice mode needs a spoken summary generated from the same verified structure that produces the screen output.
- Spoken progress markers, because thirty seconds of silence feels broken.

**Note:** this adds nothing to the interview story. The trajectory is identical whether the input string came from a keyboard or a microphone. Build it for the demo, but never let it become the headline.

---

## 6. Suggested Repository Layout

```
financial-research-agent/
  agent/
    loop.py           # the agent loop
    tools.py          # tool definitions and dispatch
    verify.py         # the verification pass
    memory.py         # notes and compaction, v3
    prompts.py
  data/
    edgar.py          # companyfacts fetching, CIK resolution
  eval/
    questions.json    # ground truth set
    runner.py
    results/
  graph/              # v4 LangGraph version
  README.md
```

---

## 7. Failure Modes To Watch For

**Adding tools because it feels like progress.** Three tools with a real evaluation set beats twelve tools with a demo video. Every tool added is another failure surface and another thing to explain.

**Building the eval set last.** Written first, the questions define what the agent has to do. Written last, they get shaped to match whatever the agent already does, which makes them worthless.

**Letting the model do arithmetic.** It will look right most of the time, which is worse than being obviously wrong.

**Fighting the finance domain instead of the agent.** Restatements, non GAAP reconciliation, and parsing operating expense tables out of a 10-Q are real problems, but they teach you nothing about agents. Stay inside XBRL until v3 is finished.

**Skipping v0 because a framework would be faster.** It would be faster. That is the reason to skip the framework, not the reason to use it.

---

## 8. How To Talk About It

**Resume bullet shape:**

> Built a verified financial research agent over SEC XBRL data with programmatic citation checking, reducing citation hallucination rate from X percent to Y percent across a hand verified 25 question evaluation suite.

**LinkedIn post shape:** lead with the number, not the architecture. Everyone posts architecture diagrams. Almost nobody posts a measured before and after on hallucination rate, and that is the thing practitioners stop scrolling for.

**Interview answer shape:** the strongest thing you can say about this project is where you decided *not* to use an agent. Fetching is deterministic. Verification is deterministic. Only the investigation sequence is agentic. Knowing where the model does not belong is a stronger signal than knowing how to chain twelve tools together.

---

## 9. Start Here

Do not open an editor yet. Write five of the evaluation questions first, and verify the answers by hand against the filings. They will tell you more about what to build than any architecture diagram will.