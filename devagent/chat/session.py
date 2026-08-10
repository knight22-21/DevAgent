import asyncio
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from devagent.chat.history import ConversationHistory
from devagent.chat.context import build_system_prompt
from devagent.core.models import GapReport
from devagent.core.config import DevAgentConfig
from devagent.core.llm import get_llm

console = Console()

class ChatSession:
    def __init__(self, report: GapReport, config: DevAgentConfig, project_name: str):
        self.report = report
        self.config = config
        self.project_name = project_name
        self.llm = get_llm(config)
        system_prompt = build_system_prompt(report, project_name)
        self.history = ConversationHistory(system_prompt, max_tokens=6000)

    async def run(self) -> None:
        """Main chat loop. Runs until user exits."""
        self._print_welcome()

        while True:
            try:
                user_input = await self._get_input()
            except (KeyboardInterrupt, EOFError):
                self._print_goodbye()
                break

            if not user_input.strip():
                continue

            # Handle special commands
            command_handled = self._handle_special_command(user_input.strip().lower())
            if command_handled == "exit":
                self._print_goodbye()
                break
            if command_handled:
                continue

            # Normal message — get LLM response
            self.history.add_user_message(user_input)

            with console.status("[dim]Thinking...[/dim]", spinner="dots"):
                try:
                    response = await self._get_llm_response()
                except Exception as e:
                    console.print(f"[red]Error getting response:[/red] {e}")
                    # Remove the user message we just added since we have no response
                    self.history.messages.pop()
                    continue

            self.history.add_assistant_message(response)
            self._print_response(response)

    async def _get_input(self) -> str:
        """Gets user input. Uses asyncio.get_event_loop().run_in_executor
        to avoid blocking the event loop."""
        loop = asyncio.get_event_loop()
        console.print()
        console.print("[bold cyan]  You ❯[/bold cyan] ", end="")
        return await loop.run_in_executor(None, input)

    async def _get_llm_response(self) -> str:
        """Calls the LLM with the full conversation history."""
        messages = self.history.to_langchain_messages()
        loop = asyncio.get_event_loop()
        # Run LLM call in executor to avoid blocking
        response = await loop.run_in_executor(
            None,
            lambda: self.llm.invoke(messages)
        )
        return response.content

    def _handle_special_command(self, command: str) -> str | bool:
        """
        Handles built-in chat commands.
        Returns "exit" to signal exit, True if handled, False if not a command.
        """
        if command in ("exit", "quit", "q", ":q", "bye"):
            return "exit"

        if command in ("help", "?"):
            self._print_help()
            return True

        if command in ("summary", "/summary"):
            self._print_report_summary()
            return True

        if command in ("conflicts", "/conflicts"):
            self._print_conflicts()
            return True

        if command in ("order", "/order"):
            self._print_implementation_order()
            return True

        if command in ("estimate", "/estimate"):
            self._print_effort_estimate()
            return True

        if command in ("clear", "/clear"):
            self.history.messages.clear()
            console.print("[dim]Conversation history cleared.[/dim]")
            return True

        return False

    def _print_welcome(self) -> None:
        console.print()
        console.print(Panel(
            "[bold]DevAgent Chat[/bold]  ·  Ask anything about this analysis\n"
            "[dim]Commands: /summary  /conflicts  /order  /estimate  /clear  exit[/dim]",
            border_style="cyan",
            padding=(0, 2)
        ))

    def _print_response(self, response: str) -> None:
        console.print()
        console.print(Panel(
            Markdown(response),
            border_style="dim",
            title="[dim]DevAgent[/dim]",
            title_align="left",
            padding=(1, 2)
        ))

    def _print_goodbye(self) -> None:
        console.print()
        console.print("[dim]Chat session ended.[/dim]")
        console.print()

    def _print_help(self) -> None:
        from rich.table import Table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("[cyan]/summary[/cyan]", "Show the full gap report summary")
        table.add_row("[cyan]/conflicts[/cyan]", "List all conflicts and affected files")
        table.add_row("[cyan]/order[/cyan]", "Show recommended implementation order")
        table.add_row("[cyan]/estimate[/cyan]", "Show effort estimate breakdown")
        table.add_row("[cyan]/clear[/cyan]", "Clear conversation history")
        table.add_row("[cyan]exit[/cyan]", "End the chat session")
        console.print(Panel(table, title="[dim]Available Commands[/dim]", border_style="dim"))

    def _print_report_summary(self) -> None:
        """Re-renders a compact version of the gap report."""
        from devagent.output.chat_renderer import render_gap_report_compact
        render_gap_report_compact(self.report)

    def _print_conflicts(self) -> None:
        """Shows just the conflicts section."""
        from devagent.output.chat_renderer import render_conflicts_only
        render_conflicts_only(self.report)

    def _print_implementation_order(self) -> None:
        for i, step in enumerate(self.report.implementation_order, 1):
            console.print(f"  [dim]{i}.[/dim] {step}")

    def _print_effort_estimate(self) -> None:
        e = self.report.effort_estimate
        from rich.table import Table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_row("Conflict resolution", f"{e.conflict_resolution_hours}h")
        table.add_row("Extensions", f"{e.extension_hours}h")
        table.add_row("Net new work", f"{e.net_new_hours}h")
        table.add_row("Testing", f"{e.testing_hours}h")
        table.add_row("[bold]Total[/bold]", f"[bold]{e.total_days} days[/bold]")
        table.add_row("Confidence", e.confidence)
        console.print(Panel(table, title="[dim]Effort Estimate[/dim]", border_style="dim"))
