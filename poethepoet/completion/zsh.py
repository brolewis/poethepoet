"""
Zsh shell completion script generation for poethepoet.

The completion script is generated dynamically from the argparse configuration
and uses zsh's _arguments and _describe completion functions.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from argparse import Action
    from collections.abc import Iterable


# Zsh code for detecting target directory and current task from command line
# Must run BEFORE _arguments since $words gets modified in state handlers
_TARGET_PATH_LOGIC = """
    local DIR_ARGS=("-C" "--directory" "--root")

    local target_path=""
    local current_task=""

    # Find target_path from -C/--directory/--root and potential task
    for ((i=2; i<${#words[@]}; i++)); do
        if (( $DIR_ARGS[(Ie)${words[i]}] )); then
            if (( ($i+1) >= ${#words[@]} )); then
                _files
                return
            fi
            target_path="${words[i+1]}"
            i=$i+1
        elif [[ "${words[i]}" != -* && -z "$current_task" ]]; then
            # First non-option word is potential task (validated later if needed)
            current_task="${words[i]}"
        fi
    done
"""


def _get_task_args_completion(name: str) -> str:
    """
    Generate zsh code for task-specific argument completion using _arguments.

    Parses tab-separated output from `poe _zsh_task_args`:
        <options>\\t<type>\\t<help>\\t<choices>

    Handles:
    - Boolean flags: no value placeholder
    - Value options (string/integer/float): with value placeholder or choices
    - Positional args: file completion or choices
    - Multiple option forms: mutual exclusivity
    """
    return f"""\
            # Complete task-specific arguments using _arguments
            local -a arg_specs
            local opts arg_type help_text choices val_compl

            [[ -z "$current_task" ]] && {{ _files; return; }}

            while IFS=$'\\t' read -r opts arg_type help_text choices; do
                [[ -z "$opts" ]] && continue

                # Build value completion spec: use choices if available
                if [[ -n "$choices" ]]; then
                    val_compl=":value:($choices)"
                else
                    val_compl=":value:()"
                fi

                if [[ "$opts" == *,* ]]; then
                    # Multiple option forms - split and add with mutual exclusivity
                    local -a opt_arr=(${{(s:,:)opts}})
                    local excl="(${{(j: :)opt_arr}})"

                    for opt in $opt_arr; do
                        case "$arg_type" in
                            boolean)
                                arg_specs+=("${{excl}}${{opt}}"'['"$help_text"']')
                                ;;
                            *)
                                arg_specs+=("${{excl}}${{opt}}"'['"$help_text"']'"$val_compl")
                                ;;
                        esac
                    done
                else
                    # Single option form
                    case "$arg_type" in
                        boolean)
                            arg_specs+=("$opts"'['"$help_text"']')
                            ;;
                        positional)
                            # Use choices if available, otherwise file completion
                            if [[ -n "$choices" ]]; then
                                if [[ -n "$help_text" ]]; then
                                    arg_specs+=(":$opts -- $help_text:($choices)")
                                else
                                    arg_specs+=(":$opts:($choices)")
                                fi
                            else
                                if [[ -n "$help_text" ]]; then
                                    arg_specs+=(":$opts -- $help_text:_files")
                                else
                                    arg_specs+=(":$opts:_files")
                                fi
                            fi
                            ;;
                        *)
                            arg_specs+=("$opts"'['"$help_text"']'"$val_compl")
                            ;;
                    esac
                fi
            done < <({name} _zsh_task_args "$current_task" $target_path 2>/dev/null)

            # Fallback to _files if no args defined
            if (( ${{#arg_specs[@]}} == 0 )); then
                _files
            else
                _arguments -s "${{arg_specs[@]}}" '*:file:_files'
            fi
    """


def _format_global_options(
    options: "list[Action]",
    excl_groups: "list[set[Action]]",
) -> list[str]:
    """
    Format global CLI options for zsh _arguments.

    Returns a list of argument spec strings for _arguments -C.
    Handles mutual exclusivity and special cases (help, version).
    """

    def format_exclusions(excl_option_strings: set[str]) -> str:
        return f"($ALL_EXLC {' '.join(sorted(excl_option_strings))})"

    args_lines = ["    _arguments -C"]

    for option in options:
        if option.help == "==SUPPRESS==":
            continue

        # help and version are special cases that don't go with other args
        if option.dest in ["help", "version"]:
            options_part = (
                option.option_strings[0]
                if len(option.option_strings) == 1
                else '"{' + ",".join(sorted(option.option_strings)) + '}"'
            )
            args_lines.append(f'"(- *){options_part}[{option.help}]"')
            continue

        # collect other options that are exclusive to this one
        excl_options: Iterable[Any] = next(
            (
                excl_group - {option}
                for excl_group in excl_groups
                if option in excl_group
            ),
            (),
        )
        # collect all option strings that are exclusive with this one
        excl_option_strings: set[str] = {
            option_string
            for excl_option in excl_options
            for option_string in excl_option.option_strings
        } | set(option.option_strings)

        if len(excl_option_strings) == 1:
            options_part = option.option_strings[0]
        elif len(option.option_strings) == 1:
            options_part = (
                format_exclusions(excl_option_strings) + option.option_strings[0]
            )
        else:
            options_part = (
                format_exclusions(excl_option_strings)
                + '"{'
                + ",".join(sorted(option.option_strings))
                + '}"'
            )

        # Check if option takes a value (nargs=0 means no value, like store_true)
        # Options with const but no nargs are also no-value (store_const)
        takes_value = option.nargs != 0 and not (
            option.const is not None and option.nargs is None and option.type is None
        )

        if takes_value:
            # Add value placeholder - use _files for directory options, empty for others
            if option.dest == "project_root":
                args_lines.append(f'"{options_part}[{option.help}]:directory:_files"')
            else:
                args_lines.append(f'"{options_part}[{option.help}]:value:()"')
        else:
            args_lines.append(f'"{options_part}[{option.help}]"')

    # State transitions for task and args completion
    args_lines.append('"1: :->task"')
    args_lines.append('"*::arg:->args"')

    return args_lines


def get_zsh_completion_script(name: str = "") -> str:
    """
    Generate a zsh completion script for poe.

    The script provides completion for:
    - Global CLI options (from argparse)
    - Task names with descriptions
    - Task-specific arguments (options and positionals)
    """
    from pathlib import Path

    from ..app import PoeThePoet

    name = name or "poe"

    # Build and interrogate the argument parser as the normal CLI would
    app = PoeThePoet(cwd=Path().resolve())
    parser = app.ui.build_parser()
    global_options = parser._action_groups[1]._group_actions
    excl_groups = [
        set(excl_group._group_actions)
        for excl_group in parser._mutually_exclusive_groups
    ]

    args_lines = _format_global_options(global_options, excl_groups)

    # Task state: load descriptions only when completing task names
    task_state_handler = f"""\
            local -a task_descriptions
            task_descriptions=(${{(f)"$({name} _zsh_describe_tasks $target_path)"}})
            _describe 'task' task_descriptions"""

    return "\n".join(
        [
            f"#compdef _{name} {name}\n",
            f"function _{name} {{",
            "    local state",
            _TARGET_PATH_LOGIC,
            '    local ALL_EXLC=("-h" "--help" "--version")',
            "",
            " \\\n        ".join(args_lines),
            "",
            "    case $state in",
            "        (task)",
            task_state_handler,
            "            ;;",
            "        (args)",
            _get_task_args_completion(name),
            "            ;;",
            "    esac",
            "}",
        ]
    )
