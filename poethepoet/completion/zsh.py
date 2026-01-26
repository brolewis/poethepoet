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
    # Other options that take a value (must skip their value when finding task name)
    local VALUE_OPTS=("-e" "--executor" "-h" "--help" "-X" "--executor-opt")

    local target_path=""
    local current_task=""
    local after_separator=0

    # Initialize session caches if not exists (persist across completion invocations)
    (( ${+_poe_task_desc_cache} )) || typeset -gA _poe_task_desc_cache
    (( ${+_poe_task_args_cache} )) || typeset -gA _poe_task_args_cache
    (( ${+_poe_cache_time} )) || typeset -g _poe_cache_time=$SECONDS

    # Check TTL - clear if expired (1 hour = 3600 seconds)
    if (( SECONDS - _poe_cache_time > 3600 )); then
        _poe_task_desc_cache=()
        _poe_task_args_cache=()
        _poe_cache_time=$SECONDS
    fi

    # Find target_path from -C/--directory/--root, potential task, and -- separator
    for ((i=2; i<${#words[@]}; i++)); do
        if [[ "${words[i]}" == "--" ]]; then
            after_separator=1
            break
        fi
        if (( $DIR_ARGS[(Ie)${words[i]}] )); then
            if (( ($i+1) >= ${#words[@]} )); then
                _files
                return
            fi
            target_path="${words[i+1]}"
            i=$i+1
        elif (( $VALUE_OPTS[(Ie)${words[i]}] )); then
            # Skip the value for this option (don't treat it as task name)
            i=$i+1
        elif [[ "${words[i]}" != -* && -z "$current_task" ]]; then
            # First non-option word is potential task (validated later if needed)
            current_task="${words[i]}"
        fi
    done

    # After --, only offer file completions (pass-through args to task)
    if (( after_separator )); then
        _files
        return
    fi
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
    - Option filtering: skip options that have already been used
    """
    return f"""\
            # Complete task-specific arguments using _arguments
            local -a arg_specs
            local opts arg_type help_text choices val_compl

            [[ -z "$current_task" ]] && {{ _files; return; }}

            # Count existing options in command line for filtering
            local -A option_counts
            for ((i=2; i<${{#words[@]}}; i++)); do
                local w="${{words[i]}}"
                [[ "$w" == -* && "$w" != "--" ]] && (( option_counts[$w]++ ))
            done

            # Check cache for task args
            local args_cache_key="${{target_path:-_default_}}|$current_task"
            local task_args_data
            if [[ -v _poe_task_args_cache[$args_cache_key] ]]; then
                task_args_data="${{_poe_task_args_cache[$args_cache_key]}}"
            else
                task_args_data="$({name} _zsh_task_args "$current_task" $target_path 2>/dev/null)"
                _poe_task_args_cache[$args_cache_key]="$task_args_data"
            fi

            while IFS=$'\\t' read -r opts arg_type help_text choices; do
                [[ -z "$opts" ]] && continue

                # Convert "_" placeholder back to empty (zsh read skips consecutive tabs)
                [[ "$choices" == "_" ]] && choices=""

                # Skip options that have already been used (positional args have their own rules)
                # BUT: don't skip if we're completing the value for this option (prev word is the option)
                if [[ "$arg_type" != "positional" ]]; then
                    local prev_word="${{words[CURRENT-1]}}"
                    local -a opt_arr=(${{(s:,:)opts}})

                    # Check if we're completing value for this option
                    local completing_value=0
                    for opt in $opt_arr; do
                        [[ "$prev_word" == "$opt" ]] && completing_value=1
                    done

                    # Only filter if not completing value for this option
                    if (( ! completing_value )); then
                        local total_count=0
                        for opt in $opt_arr; do
                            (( total_count += ${{option_counts[$opt]:-0}} ))
                        done
                        # Skip if already used
                        (( total_count >= 1 )) && continue
                    fi
                fi

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
            done <<< "$task_args_data"

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

        # help and version are mutually exclusive with each other, but can follow other options
        # (e.g., `poe -C path --help` should work)
        if option.dest == "help":
            # --help can optionally take a task name
            options_part = (
                option.option_strings[0]
                if len(option.option_strings) == 1
                else '"{' + ",".join(sorted(option.option_strings)) + '}"'
            )
            args_lines.append(
                f'"($ALL_EXLC){options_part}[{option.help}]::task:->help_task"'
            )
            continue

        if option.dest == "version":
            options_part = (
                option.option_strings[0]
                if len(option.option_strings) == 1
                else '"{' + ",".join(sorted(option.option_strings)) + '}"'
            )
            args_lines.append(f'"($ALL_EXLC){options_part}[{option.help}]"')
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
            # Add value placeholder based on option type
            if option.dest == "project_root":
                args_lines.append(f'"{options_part}[{option.help}]:directory:_files"')
            elif option.dest == "executor":
                # Known executor types
                args_lines.append(
                    f'"{options_part}[{option.help}]'
                    ':executor:(auto poetry simple uv virtualenv)"'
                )
            elif option.dest == "executor_options":
                # -X/--executor-opt takes arbitrary key=value, no useful completion
                args_lines.append(f'"{options_part}[{option.help}]"')
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

    # Task state: load descriptions only when completing task names (with caching)
    task_state_handler = f"""\
            # Don't show tasks if user is typing an option (starts with -)
            [[ ${{words[CURRENT]}} == -* ]] && return

            local -a task_descriptions
            local cache_key="${{target_path:-_default_}}"
            if [[ -v _poe_task_desc_cache[$cache_key] ]]; then
                task_descriptions=(${{(f)_poe_task_desc_cache[$cache_key]}})
            else
                local result
                result="$({name} _zsh_describe_tasks $target_path 2>/dev/null)"
                _poe_task_desc_cache[$cache_key]="$result"
                task_descriptions=(${{(f)result}})
            fi
            _describe 'task' task_descriptions"""

    # help_task state: offer task names for --help [task] (with caching)
    help_task_state_handler = f"""\
            local -a task_descriptions
            local cache_key="${{target_path:-_default_}}"
            if [[ -v _poe_task_desc_cache[$cache_key] ]]; then
                task_descriptions=(${{(f)_poe_task_desc_cache[$cache_key]}})
            else
                local result
                result="$({name} _zsh_describe_tasks $target_path 2>/dev/null)"
                _poe_task_desc_cache[$cache_key]="$result"
                task_descriptions=(${{(f)result}})
            fi
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
            "        (help_task)",
            help_task_state_handler,
            "            ;;",
            "        (args)",
            _get_task_args_completion(name),
            "            ;;",
            "    esac",
            "}",
            "",
            f"compdef _{name} {name}",
        ]
    )
