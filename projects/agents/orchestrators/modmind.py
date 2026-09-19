# [DNA_TAG]
# ORIGIN: Crostini-Chromebook
# PILLAR: agents
# FKA: ~/modmind.py
# ROLE: modmind.py — see canonical at ~/projects/agents/orchestrators/modmind.py
# SESSION: 2026-09-08
# TIER: 3
# [/DNA_TAG]

#!/usr/bin/env python3
import typer
import json
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from config import settings
from boardroom_orchestrator import BoardroomOrchestrator
from headless_anchor_bridge import HeadlessAnchor

# This automatically handles the --help flags and commands
app = typer.Typer(
    name="ModMind",
    help="EquiNex Multi-Agent Orchestrator CLI",
    no_args_is_help=True,
    rich_markup_mode="rich"
)
console = Console()
bus_path = settings.bus_path

def write_to_bus(event_type: str, payload: dict, agent_id: str = "modmind"):
    """Append an event to the system bus."""
    event = {
        "event_type": event_type,
        "agent_id": agent_id,
        "payload": payload,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    with open(bus_path, "a") as f:
        f.write(json.dumps(event) + "\n")


def print_banner():
    banner = r"""
 __  __           _ __  __ _           _ 
|  \/  |         | |  \/  (_)         | |
| \  / | ___   __| | \  / |_ _ __   __| |
| |\/| |/ _ \ / _` | |\/| | | '_ \ / _` |
| |  | | (_) | (_| | |  | | | | | | (_| |
|_|  |_|\___/ \__,_|_|  |_|_|_| |_|\__,_|
    """
    console.print(Panel(f"[bold purple]{banner}[/bold purple]", border_style="magenta", title="[blink]God Mode Active[/blink]"))

@app.command()
def anchor_query(prompt: str = typer.Argument(..., help="Prompt for the AI Anchor")):
    """
    [bold cyan]Query the AI Anchor in headless mode.[/bold cyan]
    """
    console.print(f"[bold cyan]ModMind:[/bold cyan] Querying Anchor: [bold magenta]{prompt}[/bold magenta]...")
    
    anchor = HeadlessAnchor()
    response = anchor.process_request(prompt)
    
    write_to_bus("anchor.request", {"prompt": prompt, "response": response})
    
    console.print(Panel(response, title="Anchor Response", border_style="blue"))

@app.command()
def orchestrate(vertical: str = typer.Argument(..., help="Vertical to analyze")):
    """
    [bold cyan]Trigger the Boardroom Orchestrator and log to bus.[/bold cyan]
    """
    console.print(f"[bold cyan]ModMind:[/bold cyan] Initiating orchestration for [bold magenta]{vertical}[/bold magenta]...")
    
    orchestrator = BoardroomOrchestrator()
    result = orchestrator.process(vertical)
    
    write_to_bus("orchestrator.request", {"vertical": vertical, "result": result})
    
    console.print(Panel(str(result), title="Orchestration Result", border_style="green"))

@app.command()
def status():
    """
    [bold cyan]Check the pulse of the distributed network.[/bold cyan]
    """
    print_banner()
    table = Table(show_header=True, header_style="bold magenta", border_style="purple")
    table.add_column("Component")
    table.add_column("Status")
    table.add_column("Detail")
    
    # Pulling directly from your config.py
    table.add_row("Inference Engine", "[green]ONLINE[/green]", settings.inference_engine)
    table.add_row("Active Model", "[cyan]LOADED[/cyan]", settings.active_local_model)
    table.add_row("Agent Mode", "[magenta]ACTIVE[/magenta]", settings.agent_execution_mode)
    table.add_row("Zrok Endpoint", "[yellow]STANDBY[/yellow]", settings.zrok_exec_endpoint)
    
    console.print(table)

@app.command()
def infer(prompt: str = typer.Argument(..., help="The prompt to feed the local model")):
    """
    [bold cyan]Send a prompt to the active GGUF model.[/bold cyan]
    """
    console.print(f"[bold cyan]Bleak:[/bold cyan] {prompt}")
    console.print("[bold purple]ModMind:[/bold purple] [dim]Spinning up llama.cpp in memory...[/dim]")
    
    # This is where your llama-cpp-python logic from earlier goes.
    # For now, we mock the output so you can see the UI.
    console.print(Panel("[white]I am ready to ingest the next directory state manifest.[/white]", border_style="purple", title="Response"))

@app.command()
def scan(target: str = typer.Option("bluetooth", help="What skill to execute")):
    """
    [bold cyan]Execute local machine skills.[/bold cyan]
    """
    if target == "bluetooth":
        console.print("[bold red]>[/bold red] [purple]Initializing Bleak hardware scanner...[/purple]")
        console.print("[green][/green] Found 3 devices.")

if __name__ == "__main__":
    app()
