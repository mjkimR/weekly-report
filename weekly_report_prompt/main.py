import argparse

from weekly_report_prompt.git_data_collector import GitDataCollector
from weekly_report_prompt.prompt_generator import PromptGenerator
from weekly_report_prompt.report_file_manager import ReportFileManager
from weekly_report_prompt.schemas import CommitDataSummary
from datetime import datetime, timedelta
from weekly_report_prompt.config_loader import ConfigLoader
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="weekly-report-prompt",
        description="Generate an LLM prompt for a weekly development report from Git history.",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="Collect commits and render the prompt, but write nothing to disk.",
    )
    parser.add_argument(
        "--config",
        dest="config_path",
        help="Path to config.yaml (default: config/config.yaml).",
    )
    parser.add_argument(
        "--template",
        dest="template_path",
        help="Path to the report template (default: config/template.md).",
    )
    parser.add_argument(
        "--build-dir",
        dest="build_dir",
        help="Directory holding prompts, reports and history (default: build/).",
    )
    return parser.parse_args(argv)


def summarize_commit_data(commits):
    """Generate summary information for Git data."""
    return CommitDataSummary(
        start_date=min([commit.date for commit in commits], default=datetime.now()),
        end_date=max([commit.date for commit in commits], default=datetime.now()),
        total_commits=len(commits),
        total_insertions=sum(commit.stats.insertions for commit in commits),
        total_deletions=sum(commit.stats.deletions for commit in commits),
        # A file touched by three commits is one changed file, not three.
        total_files_changed=len(
            {path for commit in commits for path in commit.stats.changed_files}
        ),
    )


# Create ConfigLoader instance and load settings
def main(argv=None):
    args = parse_args(argv)
    console = Console(force_terminal=True, color_system="truecolor")

    # Welcome message
    welcome_panel = Panel(
        Text("Weekly Report Prompt Generator", style="bold blue"),
        subtitle="Generating prompt for weekly development report",
        border_style="blue",
    )
    console.print(welcome_panel)

    # Initialize components
    console.print("Initializing configuration...")
    config = ConfigLoader(
        config_path=args.config_path, template_path=args.template_path
    )
    repo_paths = config.get_repositories()
    file_mgr = ReportFileManager(config_loader=config, build_dir=args.build_dir)

    # Everything up to the write phase below is read-only: a run that finds no commits,
    # or a --dry-run, must leave the build directory exactly as it found it.
    console.print("Reading previous reports...")
    previous_reports = file_mgr.fetch_report_history()
    memo = file_mgr.fetch_memo()

    # Set the starting point based on the last report date
    console.print("Determining report date range...")
    last_report_date = file_mgr.get_last_report_date()
    if not last_report_date:
        console.print(
            "[yellow]⚠️  No previous report found. Collecting commits from the last 7 days.[/yellow]"
        )
        last_report_date = (datetime.now() - timedelta(days=7)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    else:
        console.print(
            f"[green]📅 Using last report date: {last_report_date.strftime('%Y-%m-%d %H:%M:%S')}[/green]"
        )

    # Display the actual reference period
    console.print(
        f"[cyan]📊 Data collection period: {last_report_date.strftime('%Y-%m-%d %H:%M:%S')} ~ Now [/cyan]"
    )

    # Collect data from repositories
    console.print("Collecting commit data...")
    project_data = []

    for repo_path in repo_paths:
        project_name = repo_path.rstrip("/").split("/")[-1]
        console.print(f"Collecting data from {project_name}...")

        collector = GitDataCollector(config_loader=config, repo_path=repo_path)
        recent_commits = collector.collect_commits(since_date=last_report_date)
        summary_data = summarize_commit_data(recent_commits)

        project_data.append(
            {
                "project_name": project_name,
                "repo_path": repo_path,
                "recent_commits": recent_commits,
                "summary": summary_data,
            }
        )

        # Show progress for each repository
        commit_count = len(recent_commits)
        if commit_count > 0:
            console.print(
                f"[green]✅ {project_name}: {commit_count} commits found[/green]"
            )
        else:
            console.print(f"[dim]⚪ {project_name}: No commits found[/dim]")

    # Create summary table
    summary_table = Table(
        title="Repository Summary", show_header=True, header_style="bold magenta"
    )
    summary_table.add_column("Project", style="cyan")
    summary_table.add_column("Commits", justify="right", style="green")
    summary_table.add_column("Insertions", justify="right", style="green")
    summary_table.add_column("Deletions", justify="right", style="red")
    summary_table.add_column("Files Changed", justify="right", style="yellow")

    total_commits = 0
    total_insertions = 0
    total_deletions = 0
    total_files = 0

    for project in project_data:
        summary = project["summary"]
        total_commits += summary.total_commits
        total_insertions += summary.total_insertions
        total_deletions += summary.total_deletions
        total_files += summary.total_files_changed

        summary_table.add_row(
            project["project_name"],
            str(summary.total_commits),
            str(summary.total_insertions),
            str(summary.total_deletions),
            str(summary.total_files_changed),
        )

    # Add total row
    summary_table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{total_commits}[/bold]",
        f"[bold]{total_insertions}[/bold]",
        f"[bold]{total_deletions}[/bold]",
        f"[bold]{total_files}[/bold]",
        style="bold",
    )

    console.print(summary_table)

    # Check if any commits were found
    if not project_data or all(len(p["recent_commits"]) == 0 for p in project_data):
        error_panel = Panel(
            "[red]❌ No commits found in the specified period.[/red]\n"
            "[yellow]Please check the author configuration or adjust the time period.[/yellow]\n"
            "[dim]Nothing was written; your previous prompt and report are untouched.[/dim]",
            title="Error",
            border_style="red",
        )
        console.print(error_panel)
        raise SystemExit(1)

    # Generate prompt
    console.print("Generating prompt...")
    prompt_gen = PromptGenerator(
        project_data=project_data,
        config_loader=config,
        previous_reports=previous_reports,
        memo=memo,
    )
    final_prompt_for_llm = prompt_gen.generate_prompt()

    # Get approximate token counts (Using tiktoken: May differ from the number of tokens used by the LLM model)
    token_counts = prompt_gen.count_approximate_tokens(final_prompt_for_llm)
    if token_counts > config.get_large_prompt_tokens():
        console.print(
            f"[yellow]⚠️ The prompt is very large ({token_counts} tokens), which may lead to high costs or errors when using the LLM model.[/yellow]\n"
            "[yellow]Consider adjusting the max_diff_lines setting in config.yaml to reduce the size of the prompt,[/yellow]\n"
            "[yellow]or raise large_prompt_tokens if your model has room for it.[/yellow]"
        )

    if args.dry_run:
        prompt_count = len(file_mgr.previous_prompt_files())
        report_count = len(file_mgr.pending_report_files())
        dry_run_panel = Panel(
            "[yellow]🧪 Dry run: nothing was written.[/yellow]\n"
            f"[blue]📝 Approximate token count: {token_counts}[/blue]\n"
            f"[dim]A real run would clear {prompt_count} previous prompt file(s), "
            f"archive or discard {report_count} report file(s) in the build directory, "
            "then write a new prompt and a blank report.[/dim]",
            title="Dry run",
            border_style="yellow",
        )
        console.print(dry_run_panel)
        return

    # Write phase: from here on the build directory is modified.
    console.print("Saving files...")
    file_mgr.clear_previous_prompts()
    file_mgr.move_previous_reports()
    file_mgr.save_prompt(final_prompt_for_llm)
    file_mgr.create_report_file()
    file_mgr.ensure_memo_file()

    # Success message
    prompt_file_path = file_mgr.prompt_file_path
    success_panel = Panel(
        "[green]🎉 Weekly report prompt generation completed successfully![/green]\n"
        f"[cyan]📊 Data period: {last_report_date.strftime('%Y-%m-%d %H:%M:%S')} ~ Now [/cyan]\n"
        f"[blue]📝 Approximate token count: {token_counts}[/blue]\n"
        "[dim]Token count is calculated using tiktoken and is for reference only. The actual number of tokens used by the LLM model may differ.[/dim]\n"
        "[dim]Check the generated prompt and template files in your output directory.[/dim]",
        title="Success",
        border_style="green",
    )
    console.print(success_panel)
    if prompt_file_path:
        console.print(f"[magenta]📄 Prompt file: {prompt_file_path}[/magenta]")


if __name__ == "__main__":
    main()
