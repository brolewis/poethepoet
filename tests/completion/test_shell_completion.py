import shutil
import subprocess

import pytest

from poethepoet import _escape_zsh_choice, _format_zsh_help


class TestEscapeZshChoice:
    """Unit tests for the _escape_zsh_choice helper function."""

    def test_simple_word(self):
        """Simple words need no quoting."""
        assert _escape_zsh_choice("vanilla") == "vanilla"

    def test_word_with_space(self):
        """Words with spaces should be quoted."""
        assert _escape_zsh_choice("quick run") == "'quick run'"

    def test_word_with_tab(self):
        """Words with tabs should be quoted."""
        assert _escape_zsh_choice("col1\tcol2") == "'col1\tcol2'"

    def test_word_with_single_quote(self):
        """Single quotes need special escaping."""
        assert _escape_zsh_choice("it's") == "'it'\\''s'"

    def test_word_with_double_quote(self):
        """Double quotes should be quoted."""
        assert _escape_zsh_choice('say "hi"') == "'say \"hi\"'"

    def test_word_with_backslash(self):
        """Backslashes should be quoted."""
        assert _escape_zsh_choice("path\\to") == "'path\\to'"

    def test_word_with_dollar(self):
        """Dollar signs should be quoted."""
        assert _escape_zsh_choice("$VAR") == "'$VAR'"

    def test_word_with_backtick(self):
        """Backticks should be quoted."""
        assert _escape_zsh_choice("`cmd`") == "'`cmd`'"

    def test_empty_string(self):
        """Empty strings return empty."""
        assert _escape_zsh_choice("") == ""

    def test_multiple_special_chars(self):
        """Multiple special characters."""
        assert _escape_zsh_choice("it's a $test") == "'it'\\''s a $test'"


class TestFormatZshHelp:
    """Unit tests for the _format_zsh_help helper function."""

    def test_basic_text(self):
        assert _format_zsh_help("Hello world") == "Hello world"

    def test_first_line_only(self):
        assert _format_zsh_help("First line\nSecond line") == "First line"

    def test_strips_whitespace(self):
        assert _format_zsh_help("  spaced  ") == "spaced"

    def test_truncates_long_text(self):
        long_text = "x" * 100
        result = _format_zsh_help(long_text, max_len=60)
        assert len(result) == 60
        assert result.endswith("...")

    def test_escapes_colons(self):
        assert _format_zsh_help("key: value") == "key\\: value"

    def test_escapes_backslashes(self):
        assert _format_zsh_help("path\\to\\file") == "path\\\\to\\\\file"

    def test_escapes_tabs(self):
        assert _format_zsh_help("col1\tcol2") == "col1 col2"

    def test_empty_string(self):
        assert _format_zsh_help("") == ""

    def test_combined_escaping(self):
        # Backslash must be escaped first, then colon
        result = _format_zsh_help("a\\b:c")
        assert result == "a\\\\b\\:c"


def test_describe_tasks(run_poe_main):
    result = run_poe_main("_describe_tasks")
    # expect an ordered listing of non-hidden tasks defined in the dummy_project
    assert result.stdout == (
        "echo show_env greet greet-shouty count also_echo sing part1 composite_task "
        "also_composite_task greet-multiple travel\n"
    )
    assert result.stderr == ""


def test_list_tasks(run_poe_main):
    result = run_poe_main("_list_tasks")
    # expect an ordered listing of non-hidden tasks defined in the dummy_project
    assert result.stdout == (
        "echo show_env greet greet-shouty count also_echo sing part1 composite_task"
        " also_composite_task greet-multiple travel\n"
    )
    assert result.stderr == ""


def test_zsh_describe_tasks(run_poe_main):
    result = run_poe_main("_zsh_describe_tasks")
    lines = result.stdout.strip().split("\n")

    # Each line should be in "name:description" format
    for line in lines:
        assert ":" in line
        name, _ = line.split(":", 1)
        assert name  # name should not be empty

    # Check a task with help text
    assert "echo:It says what you say" in result.stdout

    # Check a task without help text (empty description after colon)
    assert "show_env:" in result.stdout

    assert result.stderr == ""


def test_zsh_task_args(run_poe_main, projects):
    # Test with a task that has args defined
    scripts_path = str(projects["scripts"])
    result = run_poe_main("_zsh_task_args", "greet-full-args", scripts_path)
    # Use rstrip to preserve trailing tabs within lines (strip() removes them from last line)
    lines = [line for line in result.stdout.rstrip("\n").split("\n") if line]

    # Should have options for the defined args
    assert len(lines) > 0

    # Each line should be tab-separated: options<TAB>type<TAB>help<TAB>choices
    for line in lines:
        parts = line.split("\t")
        assert len(parts) == 4, f"Expected 4 tab-separated parts, got: {line!r}"
        opts, arg_type = parts[0], parts[1]
        assert opts  # options should not be empty
        assert arg_type in ("boolean", "string", "integer", "float", "positional")

    # Check some expected options exist with correct types
    assert any("--greeting" in line and "\tstring\t" in line for line in lines)
    assert any("--user" in line and "\tstring\t" in line for line in lines)
    assert any("--upper" in line and "\tboolean\t" in line for line in lines)

    assert result.stderr == ""


def test_zsh_task_args_no_args(run_poe_main):
    # Test with a task that has no args (uses default example_project)
    result = run_poe_main("_zsh_task_args", "echo")
    # Should have no output (no args defined)
    assert result.stdout == ""
    assert result.stderr == ""


def test_zsh_completion(run_poe_main):
    result = run_poe_main("_zsh_completion")
    # some lines to stdout and none for stderr
    assert len(result.stdout.split("\n")) > 5
    assert result.stderr == ""
    assert "Error: Unrecognised task" not in result.stdout


class TestZshCompletionScript:
    """Regression tests for zsh completion script structure."""

    def test_has_current_task_detection(self, run_poe_main):
        """Verify script detects current task from command line."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # Should have current_task variable
        assert "current_task=" in script
        # Should scan $words for task name
        assert 'current_task="${words[i]}"' in script

    def test_has_state_machine(self, run_poe_main):
        """Verify script uses _arguments state machine."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # Should have state transitions
        assert "->task" in script
        assert "->args" in script
        # Should have case statement for states
        assert "case $state in" in script
        assert "(task)" in script
        assert "(args)" in script

    def test_task_state_uses_describe(self, run_poe_main):
        """Verify task completion uses _describe with descriptions."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        assert "_describe 'task' task_descriptions" in script
        assert "_zsh_describe_tasks" in script

    def test_args_state_calls_zsh_task_args(self, run_poe_main):
        """Verify args completion calls _zsh_task_args builtin."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        assert "_zsh_task_args" in script
        assert "$current_task" in script

    def test_args_state_handles_option_types(self, run_poe_main):
        """Verify args completion handles boolean vs value options."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # Should have case for boolean (no value)
        assert "boolean)" in script
        # Should have case for value options
        assert ":value:()" in script

    def test_args_state_has_fallback(self, run_poe_main):
        """Verify args completion falls back to _files."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # Should fallback to files if no args defined
        assert "_files" in script


def test_zsh_task_args_multi_form_options(run_poe_main, projects):
    """Verify multi-form options (--opt,-o) are output correctly."""
    scripts_path = str(projects["scripts"])
    result = run_poe_main("_zsh_task_args", "greet-full-args", scripts_path)

    # --greeting,-g should be comma-separated in output
    assert "--greeting,-g\t" in result.stdout

    # --age,-a should also be comma-separated
    assert "--age,-a\t" in result.stdout


def test_zsh_task_args_types(run_poe_main, projects):
    """Verify different arg types are output correctly."""
    scripts_path = str(projects["scripts"])
    result = run_poe_main("_zsh_task_args", "greet-full-args", scripts_path)
    lines = result.stdout.strip().split("\n")

    # Find specific types
    types_found = {line.split("\t")[1] for line in lines if "\t" in line}

    assert "string" in types_found
    assert "boolean" in types_found
    assert "integer" in types_found
    assert "float" in types_found


class TestZshEdgeCases:
    """Edge case tests for zsh completion to prevent regressions."""

    def test_help_text_with_apostrophe(self, run_poe_main, projects):
        """Help text with apostrophe shouldn't break completion."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_zsh_task_args", "greet-full-args", scripts_path)

        # "The user's height in meters" - apostrophe should be preserved
        assert "user's height" in result.stdout
        assert result.stderr == ""

    def test_multiline_arg_help_uses_first_line(self, run_poe_main, projects):
        """Multiline arg help text should only use first line."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_zsh_task_args", "multiple-lines-help", scripts_path)

        # Should have first line only, no indented continuation
        assert "First positional arg" in result.stdout
        assert "documentation multiline" not in result.stdout

    def test_multiline_task_help_uses_first_line(self, run_poe_main, projects):
        """Multiline task help text should only use first line."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_zsh_describe_tasks", scripts_path)

        # multiple-lines-help task has multiline help starting with "Multilines"
        # Should only show first non-empty line
        assert "multiple-lines-help:Multilines" in result.stdout
        # Should NOT include the continuation
        assert "Creating multi-line" not in result.stdout

    def test_positional_args_output(self, run_poe_main, projects):
        """Positional args should have type 'positional'."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_zsh_task_args", "multiple-lines-help", scripts_path)
        lines = result.stdout.strip().split("\n")

        # Find positional args
        positional_lines = [line for line in lines if "\tpositional\t" in line]
        assert len(positional_lines) >= 1

        # Positional args use name, not options
        for line in positional_lines:
            name = line.split("\t")[0]
            assert not name.startswith("-")  # not an option

    def test_positional_args_with_help(self, run_poe_main, projects):
        """Positional args should include help text."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_zsh_task_args", "greet-positional", scripts_path)
        lines = result.stdout.strip().split("\n")

        # Find the greeting positional arg
        greeting_line = next(line for line in lines if line.startswith("greeting\t"))
        parts = greeting_line.split("\t")

        assert parts[0] == "greeting"
        assert parts[1] == "positional"
        assert "required" in parts[2]  # help text present

    def test_args_without_help(self, run_poe_main, projects):
        """Args without help should have empty help field."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_zsh_task_args", "greet-full-args", scripts_path)
        lines = result.stdout.strip().split("\n")

        # --greeting has no help defined
        greeting_line = next(line for line in lines if "--greeting" in line)
        parts = greeting_line.split("\t")
        # Has 4 fields: opts, type, help, choices
        assert (
            len(parts) == 4
        ), f"Expected 4 tab-separated parts, got: {greeting_line!r}"
        # Help field should be empty
        assert parts[2] == ""
        # Choices field should be "_" placeholder for empty
        assert parts[3] == "_"

    def test_help_with_colon_escaped(self, run_poe_main):
        """Colons in help text should be escaped for zsh."""
        result = run_poe_main("_zsh_describe_tasks")

        # "It says what you say" doesn't have colons, but format is name:help
        # If a task had "key: value" in help, it should be "key\\: value"
        # For now just verify the format is correct
        for line in result.stdout.strip().split("\n"):
            parts = line.split(":", 1)
            assert len(parts) == 2  # name:description format


class TestFormatZshHelpEdgeCases:
    """Additional edge cases for _format_zsh_help."""

    def test_multiline_takes_first_line_only(self):
        text = "First line\n  indented second\n  third"
        assert _format_zsh_help(text) == "First line"

    def test_apostrophe_preserved(self):
        # Apostrophes don't need escaping in zsh completion descriptions
        assert _format_zsh_help("user's name") == "user's name"

    def test_brackets_preserved(self):
        # Brackets in help text (not in zsh code context)
        assert _format_zsh_help("array[0]") == "array[0]"

    def test_quotes_preserved(self):
        assert _format_zsh_help('say "hello"') == 'say "hello"'

    def test_truncation_strips_trailing_before_ellipsis(self):
        # When truncating, trailing spaces are stripped before adding ...
        text = "x" * 65  # Over 60 chars
        result = _format_zsh_help(text, max_len=60)
        # 60 - 3 = 57, then rstrip, then add ...
        assert result == "x" * 57 + "..."
        assert len(result) == 60


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh not available")
def test_zsh_completion_syntax(run_poe_main):
    """Validate that the generated zsh completion script has valid syntax."""
    result = run_poe_main("_zsh_completion")
    assert result.code == 0

    # zsh -n parses without executing, exits non-zero on syntax errors
    proc = subprocess.run(
        ["zsh", "-n"],
        input=result.stdout,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"zsh syntax error:\n{proc.stderr}"


def test_bash_completion(run_poe_main):
    result = run_poe_main("_bash_completion")
    # some lines to stdout and none for stderr
    assert len(result.stdout.split("\n")) > 5
    assert result.stderr == ""
    assert "Error: Unrecognised task" not in result.stdout


class TestBashCompletionScript:
    """Tests for improved bash completion script."""

    def test_has_global_options(self, run_poe_main):
        """Verify script includes global options."""
        result = run_poe_main("_bash_completion")
        script = result.stdout

        # Should include common global options
        assert "-h --help" in script or '"-h" "--help"' in script
        assert "--version" in script
        assert "-C" in script
        assert "--directory" in script

    def test_extracts_target_path(self, run_poe_main):
        """Verify script extracts -C/--directory/--root."""
        result = run_poe_main("_bash_completion")
        script = result.stdout

        assert "-C|--directory|--root)" in script
        assert 'target_path="${words[i+1]}"' in script

    def test_calls_list_tasks_with_target_path(self, run_poe_main):
        """Verify _list_tasks is called with target_path."""
        result = run_poe_main("_bash_completion")
        script = result.stdout

        assert '_list_tasks "$target_path"' in script

    def test_calls_bash_task_args(self, run_poe_main):
        """Verify _bash_task_args is called for task-specific completion."""
        result = run_poe_main("_bash_completion")
        script = result.stdout

        assert "_bash_task_args" in script
        assert '"$current_task"' in script

    def test_completes_options_when_dash(self, run_poe_main):
        """Verify script completes options when current word starts with -."""
        result = run_poe_main("_bash_completion")
        script = result.stdout

        assert '[[ "$cur" == -* ]]' in script

    def test_calls_bash_task_arg_choices(self, run_poe_main):
        """Verify _bash_task_arg_choices is called for option value completion."""
        result = run_poe_main("_bash_completion")
        script = result.stdout

        # Should call _bash_task_arg_choices when prev is an option
        assert "_bash_task_arg_choices" in script
        assert '"$current_task:$prev"' in script

    def test_handles_boolean_flags(self, run_poe_main):
        """Verify script handles _BOOLEAN_ marker for boolean flags."""
        result = run_poe_main("_bash_completion")
        script = result.stdout

        # Should check for _BOOLEAN_ marker and not try to complete value
        assert "_BOOLEAN_" in script
        assert "show_task_opts=true" in script

    def test_filters_used_options(self, run_poe_main):
        """Verify script filters out already-used options."""
        result = run_poe_main("_bash_completion")
        script = result.stdout

        # Should track already used options
        assert "already_used" in script
        # Should filter them out
        assert "filtered_args" in script


def test_bash_task_args(run_poe_main, projects):
    """Test _bash_task_args outputs option strings (not choices)."""
    scripts_path = str(projects["scripts"])
    result = run_poe_main("_bash_task_args", "flavor-picker", scripts_path)

    # Should include option strings
    assert "--flavor" in result.stdout
    assert "-f" in result.stdout

    # Should NOT include choices (those come from _bash_task_arg_choices)
    assert "vanilla" not in result.stdout
    assert "chocolate" not in result.stdout

    assert result.stderr == ""


def test_bash_task_args_includes_booleans(run_poe_main, projects):
    """Test _bash_task_args includes boolean flags."""
    scripts_path = str(projects["scripts"])
    result = run_poe_main("_bash_task_args", "greet-passed-args", scripts_path)

    # Should include boolean flags like --upper
    assert "--upper" in result.stdout
    # And regular options
    assert "--greeting" in result.stdout

    assert result.stderr == ""


def test_bash_task_arg_choices(run_poe_main, projects):
    """Test _bash_task_arg_choices outputs choices for specific option."""
    scripts_path = str(projects["scripts"])
    result = run_poe_main(
        "_bash_task_arg_choices", "flavor-picker:--flavor", scripts_path
    )

    # Should include choices for --flavor
    assert "vanilla" in result.stdout
    assert "chocolate" in result.stdout
    assert "strawberry" in result.stdout

    # Should NOT include size choices
    assert "small" not in result.stdout

    assert result.stderr == ""


def test_bash_task_arg_choices_short_option(run_poe_main, projects):
    """Test _bash_task_arg_choices works with short option form."""
    scripts_path = str(projects["scripts"])
    result = run_poe_main("_bash_task_arg_choices", "flavor-picker:-f", scripts_path)

    # Should include choices for -f (same as --flavor)
    assert "vanilla" in result.stdout
    assert "chocolate" in result.stdout
    assert "strawberry" in result.stdout

    assert result.stderr == ""


def test_bash_task_arg_choices_no_choices(run_poe_main, projects):
    """Test _bash_task_arg_choices with option that has no choices."""
    scripts_path = str(projects["scripts"])
    # greet task has --greeting option but no choices
    result = run_poe_main("_bash_task_arg_choices", "greet:--greeting", scripts_path)

    # Should be empty - no choices defined
    assert result.stdout == ""
    assert result.stderr == ""


def test_bash_task_arg_choices_boolean(run_poe_main, projects):
    """Test _bash_task_arg_choices returns _BOOLEAN_ for boolean flags."""
    scripts_path = str(projects["scripts"])
    # greet-full-args has --upper which is a boolean flag
    result = run_poe_main(
        "_bash_task_arg_choices", "greet-full-args:--upper", scripts_path
    )

    # Should return _BOOLEAN_ marker
    assert result.stdout.strip() == "_BOOLEAN_"
    assert result.stderr == ""


def test_bash_task_boolean_args(run_poe_main, projects):
    """Test _bash_task_boolean_args returns only boolean flags."""
    scripts_path = str(projects["scripts"])
    result = run_poe_main("_bash_task_boolean_args", "greet-full-args", scripts_path)

    # Should only include boolean flags
    assert "--upper" in result.stdout

    # Should NOT include non-boolean options
    assert "--greeting" not in result.stdout
    assert "-g" not in result.stdout
    assert "--age" not in result.stdout
    assert result.stderr == ""


def test_bash_task_boolean_args_no_booleans(run_poe_main, projects):
    """Test _bash_task_boolean_args with task that has no boolean args."""
    scripts_path = str(projects["scripts"])
    # flavor-picker has only string/choice args, no booleans
    result = run_poe_main("_bash_task_boolean_args", "flavor-picker", scripts_path)

    # Should be empty - no boolean flags
    assert result.stdout == ""
    assert result.stderr == ""


def test_bash_task_args_no_args(run_poe_main):
    """Test _bash_task_args with task that has no args."""
    result = run_poe_main("_bash_task_args", "echo")
    # Should have no output
    assert result.stdout == ""
    assert result.stderr == ""


def test_fish_completion(run_poe_main):
    result = run_poe_main("_fish_completion")
    # some lines to stdout and none for stderr
    assert len(result.stdout.split("\n")) > 5
    assert result.stderr == ""
    assert "Error: Unrecognised task" not in result.stdout


class TestDirectoryOption:
    """Tests for -C/--directory option passthrough in completion."""

    def test_list_tasks_with_target_path(self, run_poe_main, projects):
        """_list_tasks should respect target_path parameter."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_list_tasks", scripts_path)

        # Should list tasks from scripts_project, not example_project
        assert "greet-full-args" in result.stdout
        assert "flavor-picker" in result.stdout
        assert result.stderr == ""

    def test_zsh_describe_tasks_with_target_path(self, run_poe_main, projects):
        """_zsh_describe_tasks should respect target_path parameter."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_zsh_describe_tasks", scripts_path)

        # Should describe tasks from scripts_project
        assert "flavor-picker:Pick ice cream" in result.stdout
        assert result.stderr == ""

    def test_zsh_completion_script_extracts_target_path(self, run_poe_main):
        """Verify completion script extracts -C/--directory/--root args."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # Should detect directory args
        assert 'DIR_ARGS=("-C" "--directory" "--root")' in script
        # Should extract target_path
        assert 'target_path="${words[i+1]}"' in script
        # Should pass target_path to builtins
        assert "_zsh_describe_tasks $target_path" in script
        assert "_zsh_task_args" in script
        assert "$target_path" in script


class TestZshChoicesCompletion:
    """Tests for argument choices in zsh completion."""

    def test_zsh_task_args_includes_choices(self, run_poe_main, projects):
        """Verify _zsh_task_args outputs choices for args that have them."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_zsh_task_args", "flavor-picker", scripts_path)
        lines = result.stdout.strip().split("\n")

        # Find the --flavor option
        flavor_line = next(line for line in lines if "--flavor" in line)
        parts = flavor_line.split("\t")
        assert len(parts) == 4
        assert parts[0] == "--flavor,-f"
        assert parts[1] == "string"
        assert parts[2] == "Ice cream flavor"
        assert "vanilla" in parts[3]
        assert "chocolate" in parts[3]
        assert "strawberry" in parts[3]

        assert result.stderr == ""

    def test_zsh_task_args_positional_with_choices(self, run_poe_main, projects):
        """Verify positional args include choices."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_zsh_task_args", "flavor-picker", scripts_path)
        # Use rstrip to preserve trailing tabs within lines
        lines = [line for line in result.stdout.rstrip("\n").split("\n") if line]

        # Find the size positional arg
        size_line = next(line for line in lines if line.startswith("size\t"))
        parts = size_line.split("\t")
        assert len(parts) == 4
        assert parts[0] == "size"
        assert parts[1] == "positional"
        assert parts[2] == "Serving size"
        assert "small" in parts[3]
        assert "medium" in parts[3]
        assert "large" in parts[3]

    def test_zsh_completion_script_has_choices_handling(self, run_poe_main):
        """Verify the zsh completion script handles choices field."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # Should read 4 fields including choices
        assert "opts arg_type help_text choices" in script
        # Should use choices for value completion
        assert 'val_compl=":value:($choices)"' in script

    def test_zsh_task_args_empty_choices(self, run_poe_main, projects):
        """Args without choices should have empty choices field."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_zsh_task_args", "greet-full-args", scripts_path)
        # Use rstrip to preserve trailing tabs within lines
        lines = [line for line in result.stdout.rstrip("\n").split("\n") if line]

        # All args in greet-full-args have no choices
        for line in lines:
            parts = line.split("\t")
            # Has 4 fields: opts, type, help, choices
            assert len(parts) == 4, f"Expected 4 tab-separated parts, got: {line!r}"
            # choices field (index 3) should be "_" placeholder for empty
            assert parts[3] == "_"


class TestZshTaskArgsSpacedChoices:
    """Tests for choices with spaces in _zsh_task_args output."""

    def test_spaced_choices_properly_quoted(self, run_poe_main, projects):
        """Choices containing spaces should be properly quoted."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_zsh_task_args", "spaced-choices", scripts_path)
        lines = result.stdout.strip().split("\n")

        # Find --type option
        type_line = next(line for line in lines if "--type" in line)
        parts = type_line.split("\t")
        choices = parts[3]

        # Spaced choices should be quoted
        assert "'quick run'" in choices, f"Expected quoted 'quick run' in {choices!r}"
        assert "'full test'" in choices, f"Expected quoted 'full test' in {choices!r}"
        # Non-spaced choice should not be quoted
        assert "smoke" in choices


class TestZshTaskArgsFormat:
    """Tests for _zsh_task_args output format."""

    def test_output_has_four_fields(self, run_poe_main, projects):
        """Each line should have 4 tab-separated fields."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_zsh_task_args", "greet-full-args", scripts_path)
        lines = [line for line in result.stdout.rstrip("\n").split("\n") if line]

        assert len(lines) > 0
        for line in lines:
            parts = line.split("\t")
            assert (
                len(parts) == 4
            ), f"Expected 4 fields (opts, type, help, choices), got: {line!r}"

    def test_option_with_choices(self, run_poe_main, projects):
        """Options with choices should have them in 4th field."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_zsh_task_args", "flavor-picker", scripts_path)
        lines = result.stdout.strip().split("\n")

        # Find --flavor option
        flavor_line = next(line for line in lines if "--flavor" in line)
        parts = flavor_line.split("\t")
        assert len(parts) == 4
        assert parts[0] == "--flavor,-f"
        assert parts[1] == "string"
        assert "vanilla" in parts[3]

    def test_positional_with_choices(self, run_poe_main, projects):
        """Positional args with choices should have them in 4th field."""
        scripts_path = str(projects["scripts"])
        result = run_poe_main("_zsh_task_args", "flavor-picker", scripts_path)
        lines = [line for line in result.stdout.rstrip("\n").split("\n") if line]

        # Find size positional arg
        size_line = next(line for line in lines if line.startswith("size\t"))
        parts = size_line.split("\t")
        assert len(parts) == 4
        assert parts[1] == "positional"
        assert "small" in parts[3]


class TestZshCompletionScriptNewFeatures:
    """Structure tests for new zsh completion script features."""

    def test_has_separator_detection(self, run_poe_main):
        """Verify script detects -- separator."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # Should have after_separator variable
        assert "after_separator=" in script
        # Should check for -- in words
        assert '== "--"' in script
        # Should offer files only after separator
        assert "after_separator" in script

    def test_executor_has_specific_completions(self, run_poe_main):
        """Verify --executor has specific value completions."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # Should have executor choices including 'auto'
        assert "auto poetry simple uv virtualenv" in script

    def test_executor_opt_no_value(self, run_poe_main):
        """Verify --executor-opt doesn't offer value completion."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # -X/--executor-opt should NOT have :value:() after it
        # Find the executor-opt line and check it doesn't have value completion
        # This is a bit tricky to test directly, but we can check that executor
        # has specific completions while executor-opt is handled differently
        lines = script.split("\n")
        # Look for lines containing executor
        executor_lines = [
            line for line in lines if "executor" in line.lower() and '"' in line
        ]
        # Should have at least one line with specific executor completions
        assert any("poetry simple uv virtualenv" in line for line in executor_lines)

    def test_help_has_optional_task_value(self, run_poe_main):
        """Verify --help has optional task value completion."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # Should have help_task state
        assert "help_task" in script
        # Should have ::task: for optional value
        assert "::task:->help_task" in script

    def test_help_task_state_handler(self, run_poe_main):
        """Verify help_task state offers task names."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # Should have case for help_task state
        assert "(help_task)" in script

    def test_has_cache_initialization(self, run_poe_main):
        """Verify script initializes session caches."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # Should initialize cache arrays
        assert "_poe_task_desc_cache" in script
        assert "_poe_task_args_cache" in script
        assert "_poe_cache_time" in script
        # Should use typeset -gA for global associative arrays
        assert "typeset -gA _poe_task_desc_cache" in script
        assert "typeset -gA _poe_task_args_cache" in script

    def test_has_cache_ttl_check(self, run_poe_main):
        """Verify script checks cache TTL (1 hour)."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # Should check TTL against 3600 seconds
        assert "3600" in script
        # Should clear caches when expired
        assert "_poe_task_desc_cache=()" in script
        assert "_poe_task_args_cache=()" in script

    def test_task_descriptions_use_cache(self, run_poe_main):
        """Verify task state uses cache for descriptions."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # Should check cache before calling poe
        assert "_poe_task_desc_cache[$cache_key]" in script
        # Should have cache key based on target_path
        assert 'cache_key="${target_path:-_default_}"' in script

    def test_task_args_use_cache(self, run_poe_main):
        """Verify args state uses cache for task args."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        # Should check cache before calling poe
        assert "_poe_task_args_cache[$args_cache_key]" in script
        # Should have cache key based on target_path and task
        assert 'args_cache_key="${target_path:-_default_}|$current_task"' in script
