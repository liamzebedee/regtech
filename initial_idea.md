We are going to take every australian law and regulation and annotate them for a cost of compliance and a cost of enforcement, to understand the regulatory burdens of the law.

- Costs are measured in both time, money.
- Compliance relates the parties involved to the work to comply. There may be multiple parties, each with a different cost.
- Enforcement relates to the cost born by the state.

Laws/regulations/statutes may incur costs which cannot be measured discretely as above.
For example - laws which reverse the burden of proof on speech do not impose a discrete cost, however they transfer liability to citizens. 
Leave a note - indefinite cost - for these.

## Build.

### Website.

Your goal is to build an interesting demo of this idea. I suggest:
- a website which shows an index of all legislation, ordered by date, intelligently tagged and clustered by topic area, and other metadata relevant.
- an interface to exploring the costs of bills and legislation.
-- show the time (pretty format), money (pretty format)
-- where cost is time, analyse the actor that bears the cost, and assume an hourly rate of minimum wage or something more intuitive for that actor. call this "assumed_time_value" and display alongside.

### Analysis.

Your analysis should happen via LLM. Use `claude` the CLI tool.
The dataset is https://huggingface.co/datasets/isaacus/open-australian-legal-corpus. Clone it using the `hf` tool.
Study the dataset's structure to design an approach to effectively analysing in parallel. Divide your workload.
Begin with simple small pieces of legislature to test your approach and iterate.
Through this, you will design an amazing methodology for evaluating cost of compliance and enforcement.
If necessary, use only Python/Bash for scripts.

#### Claude notes.

When using `claude`, note the following:
- Your context window is 128k tokens. At 50% saturation, Claude gets dumber. Never get to this length.
- Use the `claude` CLI for LLM interactions. Use as many `claude` invocations as you desire. You can invoke parallelism  inside Claude by asking it to use parallel subagents. Use the Sonnet model for language tasks.
- You can self-improve by designing loops for different work areas.
    - Put each loop's code in a different folder.
    - Design a loop.sh which calls claude in a while loop to read from a PROMPT.md file.
    - Design the PROMPT.md file to compare the system state aganist the desired state, read the current work item from an implementation_plan.md file containing todos and work log notes, and then work on completing that item.
    - Call loop.sh inside another `claude` instance in order to supervise the loop, which helps to resolve "infinite loops" where the agent gets stuck (among other potential design flaws).

### Project architecture and technical.

Separate the areas of design into analysis/ and app/
Store your analysis along with legislation in an SQLite database that is consumed by the website. Ensure the database is performant.
The website should be minimally built but beautiful. Use Next.js, TS, React.

