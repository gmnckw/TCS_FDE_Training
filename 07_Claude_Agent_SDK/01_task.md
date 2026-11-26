Task: 

Code Review:

You have a small Python project in task_project/. It contains shop.py and test_shop.py, and you haven't seen the code before.

Build a read-only agent with the Claude Agent SDK that reviews this project. The agent may only use the Glob, Grep and Read tools, and it must not use Bash.

Write a function scout(prompt) that runs the agent. While it runs, the function must print the name of each tool the agent uses. When the agent finishes, it must print the final report, the number of turns and the total cost.
Run scout() with two prompts that you write yourself. Don't tell the agent which tool to use.
Prompt A: list every function in the project and say which ones have no docstring.
Prompt B: report any bugs or security problems in the project, each with a one-line fix.
Answer these two questions in a markdown cell:
Did the agent find at least 3 real problems? Name them.
Which message type gave you the tool names, and why is there no ToolUseMessage?
Work in a new notebook and reuse the setup from the course notebook (.env, run_sync() and MODEL_NAME). Don't put your API key in the notebook.

Algorithm:
  Step 1: data set 
  Step 2: Implement agent 
        codereviewer(prompt):
          query(...)
  step 3: get the result printed 