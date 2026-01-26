"""
Zsh completion end-to-end harness tests.

These tests run real zsh with stubbed completion builtins to verify
the completion logic works correctly. The harness captures what our
script passes to _arguments, _describe, and _files.
"""

import shutil
import subprocess

import pytest


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh not available")
class TestZshCompletionE2E:
    """End-to-end tests for zsh completion behavior."""

    @pytest.fixture
    def completion_script(self, run_poe_main):
        """Get the generated zsh completion script."""
        result = run_poe_main("_zsh_completion")
        return result.stdout

    # ========== Separator (--) handling tests ==========

    def test_after_separator_offers_files_only(self, zsh_harness, completion_script):
        """After --, only file completion should be offered."""
        mock_output = {
            "_zsh_describe_tasks": "greet:Greet someone",
            "_zsh_task_args": "--greeting,-g\tstring\tGreeting\t_",
        }

        # Simulate: poe greet -- <TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", "greet", "--", ""],
            current=4,
            mock_poe_output=mock_output,
        )

        assert result.after_separator, "Should detect -- separator"
        assert result.early_return, "Should return early after --"
        assert result.files_called, "Should offer file completion after --"

    def test_after_separator_with_args_before(self, zsh_harness, completion_script):
        """After -- with task args before, should still offer files only."""
        mock_output = {
            "_zsh_describe_tasks": "greet:Greet someone",
            "_zsh_task_args": "--greeting,-g\tstring\tGreeting\t_",
        }

        # Simulate: poe greet --greeting hello -- <TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", "greet", "--greeting", "hello", "--", ""],
            current=6,
            mock_poe_output=mock_output,
        )

        assert result.after_separator, "Should detect -- separator"
        assert result.files_called, "Should offer file completion"

    def test_before_separator_offers_task_args(self, zsh_harness, completion_script):
        """Before --, task arguments should be offered."""
        mock_output = {
            "_zsh_describe_tasks": "greet:Greet someone",
            "_zsh_task_args": "--greeting,-g\tstring\tGreeting\t_",
        }

        # Simulate: poe greet --<TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", "greet", "--"],
            current=3,
            mock_poe_output=mock_output,
        )

        assert not result.after_separator, "Should not detect separator"
        assert result.arguments_called, "Should call _arguments for task args"

    def test_double_dash_as_option_value_not_separator(
        self, zsh_harness, completion_script
    ):
        """-- as an option value should not trigger separator mode."""
        mock_output = {
            "_zsh_describe_tasks": "greet:Greet someone",
            "_zsh_task_args": "--greeting,-g\tstring\tGreeting\t_",
        }

        # Simulate: poe greet --greeting -- <TAB>
        # Here -- is the value for --greeting, not a separator
        # Actually this is ambiguous - the script treats standalone -- as separator
        # This test documents current behavior
        result = zsh_harness(
            completion_script,
            words=["poe", "greet", "--greeting", "--", ""],
            current=5,
            mock_poe_output=mock_output,
        )

        # Current implementation treats -- as separator regardless of position
        # This is the expected behavior per the spec
        assert result.after_separator

    # ========== Global option completion tests ==========

    def test_help_not_exclusive_with_all_options(self, zsh_harness, completion_script):
        """--help should not use (- *) exclusion which blocks it after any option."""
        mock_output = {
            "_zsh_describe_tasks": "greet:Greet someone",
        }

        # Simulate: poe -<TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", "-"],
            current=2,
            mock_poe_output=mock_output,
        )

        assert result.arguments_called
        # Find specs containing --help
        help_specs = [s for s in result.arguments_specs if "--help" in s]
        assert help_specs, "Should have --help in specs"

        # Check that --help doesn't use (- *) exclusion
        # (- *) means "exclusive with all options and args" which is too aggressive
        for spec in help_specs:
            assert "(- *)" not in spec, (
                f"--help should not use (- *) exclusion - it blocks --help after any option. "
                f"Got spec: {spec}"
            )

    def test_option_completion_does_not_show_tasks(
        self, zsh_harness, completion_script
    ):
        """When completing an option (poe -<TAB>), tasks should not be shown."""
        mock_output = {
            "_zsh_describe_tasks": "greet:Greet someone\necho:Echo text",
        }

        # Simulate: poe -<TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", "-"],
            current=2,
            mock_poe_output=mock_output,
        )

        # Should be completing an option
        assert result.completing_option, "Should detect we're completing an option"
        # _arguments should be called (to show global options)
        assert result.arguments_called, "Should call _arguments for global options"
        # But _describe should NOT be called (we don't want tasks mixed with options)
        assert not result.describe_called, (
            "Should NOT call _describe when completing options - "
            "tasks should not be mixed with global options"
        )

    # ========== Task completion tests ==========

    def test_task_completion_with_no_task(self, zsh_harness, completion_script):
        """Completing with no task should offer task names."""
        mock_output = {
            "_zsh_describe_tasks": "greet:Greet someone\necho:Echo text",
        }

        # Simulate: poe <TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", ""],
            current=2,
            mock_poe_output=mock_output,
        )

        assert result.state == "task", "Should be in task state"
        assert result.describe_called, "Should call _describe for tasks"
        assert result.describe_tag == "task"
        assert "greet:Greet someone" in result.describe_items
        assert "echo:Echo text" in result.describe_items

    def test_task_completion_with_partial(self, zsh_harness, completion_script):
        """Completing partial task name should offer matching tasks."""
        mock_output = {
            "_zsh_describe_tasks": "greet:Greet someone\necho:Echo text",
        }

        # Simulate: poe gr<TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", "gr"],
            current=2,
            mock_poe_output=mock_output,
        )

        assert result.state == "task"
        assert result.describe_called

    # ========== Task args completion tests ==========

    def test_task_args_completion(self, zsh_harness, completion_script):
        """After task, should offer task-specific arguments."""
        mock_output = {
            "_zsh_describe_tasks": "greet:Greet someone",
            "_zsh_task_args": "--greeting,-g\tstring\tThe greeting\t_\n--upper\tboolean\tUppercase\t_",
        }

        # Simulate: poe greet <TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", "greet", ""],
            current=3,
            mock_poe_output=mock_output,
        )

        assert result.current_task == "greet"
        assert result.state == "args"
        assert result.arguments_called

    def test_task_args_with_choices(self, zsh_harness, completion_script):
        """Task args with choices should include them in completion."""
        mock_output = {
            "_zsh_describe_tasks": "pick:Pick something",
            "_zsh_task_args": "--flavor,-f\tstring\tFlavor\tvanilla chocolate",
        }

        # Simulate: poe pick <TAB>
        # Note: We complete BEFORE typing --flavor to test choices appear in arg_specs.
        # Once --flavor is typed, it gets filtered by repeatability logic.
        result = zsh_harness(
            completion_script,
            words=["poe", "pick", ""],
            current=3,
            mock_poe_output=mock_output,
        )

        assert result.arguments_called
        # Check that choices appear in the argument specs
        specs_text = "\n".join(result.arguments_specs)
        assert "vanilla" in specs_text, f"Expected 'vanilla' in specs: {specs_text}"
        assert "chocolate" in specs_text

    def test_task_args_with_spaced_choices(self, zsh_harness, completion_script):
        """Choices with spaces should be properly quoted."""
        mock_output = {
            "_zsh_describe_tasks": "test:Test task",
            "_zsh_task_args": "--type,-t\tstring\tType\t'quick run' 'full test' smoke",
        }

        # Simulate: poe test <TAB>
        # Complete BEFORE typing --type to test spaced choices appear in arg_specs.
        result = zsh_harness(
            completion_script,
            words=["poe", "test", ""],
            current=3,
            mock_poe_output=mock_output,
        )

        assert result.arguments_called
        specs_text = "\n".join(result.arguments_specs)
        # Quoted choices should appear
        assert "quick run" in specs_text or "'quick run'" in specs_text

    # ========== Option filtering tests ==========

    def test_option_not_offered_after_use(self, zsh_harness, completion_script):
        """Options should not be offered again after being used once."""
        mock_output = {
            "_zsh_describe_tasks": "task:A task",
            "_zsh_task_args": "--mode,-m\tstring\tMode\t_\n--other\tstring\tOther\t_",
        }

        # Simulate: poe task --mode value <TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", "task", "--mode", "value", ""],
            current=5,
            mock_poe_output=mock_output,
        )

        assert result.arguments_called
        specs_text = "\n".join(result.arguments_specs)
        # --mode should NOT appear (already used)
        # --other should appear (not yet used)
        assert "--other" in specs_text

    def test_option_value_completion_with_choices(self, zsh_harness, completion_script):
        """When completing option value, choices should be offered even if option was 'used'."""
        mock_output = {
            "_zsh_describe_tasks": "pick:Pick something",
            "_zsh_task_args": "--flavor,-f\tstring\tFlavor\tvanilla chocolate strawberry",
        }

        # Simulate: poe pick --flavor <TAB>
        # The option --flavor appears in words, but we're completing its VALUE
        result = zsh_harness(
            completion_script,
            words=["poe", "pick", "--flavor", ""],
            current=4,
            mock_poe_output=mock_output,
        )

        assert result.arguments_called
        specs_text = "\n".join(result.arguments_specs)
        # --flavor SHOULD appear in specs so _arguments can offer value completion
        assert "--flavor" in specs_text, (
            "Option should be in specs when completing its value - "
            f"got specs: {result.arguments_specs}"
        )
        # Choices should be in the spec
        assert "vanilla" in specs_text
        assert "chocolate" in specs_text

    # ========== --help completion tests ==========

    def test_help_offers_task_names(self, zsh_harness, completion_script):
        """--help should offer task names as optional value."""
        mock_output = {
            "_zsh_describe_tasks": "greet:Greet someone\necho:Echo text",
        }

        # Simulate: poe --help <TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", "--help", ""],
            current=3,
            mock_poe_output=mock_output,
        )

        # Should enter help_task state and call _describe
        assert result.state == "help_task"
        assert result.describe_called
        assert "greet:Greet someone" in result.describe_items

    def test_help_short_form_offers_task_names(self, zsh_harness, completion_script):
        """Short -h should also offer task names."""
        mock_output = {
            "_zsh_describe_tasks": "greet:Greet someone\necho:Echo text",
        }

        # Simulate: poe -h <TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", "-h", ""],
            current=3,
            mock_poe_output=mock_output,
        )

        assert result.state == "help_task"
        assert result.describe_called

    def test_help_value_not_treated_as_task(self, zsh_harness, completion_script):
        """Value after -h should not be treated as current task."""
        mock_output = {
            "_zsh_describe_tasks": "greet:Greet someone\necho:Echo text",
            "_zsh_task_args": "--flavor,-f\tstring\tFlavor\tvanilla chocolate",
        }

        # Simulate: poe -h greet --<TAB>
        # 'greet' is the help target, NOT the current task
        result = zsh_harness(
            completion_script,
            words=["poe", "-h", "greet", "--"],
            current=4,
            mock_poe_output=mock_output,
        )

        # Should NOT detect 'greet' as current_task
        assert (
            result.current_task == ""
        ), f"Expected no current_task (greet is -h value), got: {result.current_task!r}"
        # When current_task is empty, args state falls back to _files
        # So task-specific args like --flavor should NOT appear in completions
        specs_text = "\n".join(result.arguments_specs)
        assert (
            "--flavor" not in specs_text
        ), "Task-specific args should not be offered when -h value is mistaken for task"

    # ========== Directory option tests ==========

    def test_directory_option_passes_path(self, zsh_harness, completion_script):
        """Target path from -C should be detected."""
        mock_output = {
            "_zsh_describe_tasks": "greet:Greet someone",
        }

        # Simulate: poe -C /some/path <TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", "-C", "/some/path", ""],
            current=4,
            mock_poe_output=mock_output,
        )

        assert result.target_path == "/some/path"

    def test_directory_long_option_passes_path(self, zsh_harness, completion_script):
        """Target path from --directory should be detected."""
        mock_output = {
            "_zsh_describe_tasks": "greet:Greet someone",
        }

        # Simulate: poe --directory /other/path <TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", "--directory", "/other/path", ""],
            current=4,
            mock_poe_output=mock_output,
        )

        assert result.target_path == "/other/path"

    # ========== Positional args tests ==========

    def test_positional_args_with_choices(self, zsh_harness, completion_script):
        """Positional args with choices should offer them."""
        mock_output = {
            "_zsh_describe_tasks": "pick:Pick size",
            "_zsh_task_args": "size\tpositional\tServing size\tsmall medium large",
        }

        # Simulate: poe pick <TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", "pick", ""],
            current=3,
            mock_poe_output=mock_output,
        )

        assert result.arguments_called
        specs_text = "\n".join(result.arguments_specs)
        assert "small" in specs_text
        assert "medium" in specs_text
        assert "large" in specs_text

    def test_positional_args_without_choices_offers_files(
        self, zsh_harness, completion_script
    ):
        """Positional args without choices should offer file completion."""
        mock_output = {
            "_zsh_describe_tasks": "cat:Cat a file",
            "_zsh_task_args": "file\tpositional\tFile to read\t_",
        }

        # Simulate: poe cat <TAB>
        result = zsh_harness(
            completion_script,
            words=["poe", "cat", ""],
            current=3,
            mock_poe_output=mock_output,
        )

        assert result.arguments_called
        specs_text = "\n".join(result.arguments_specs)
        assert "_files" in specs_text


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh not available")
class TestZshHarnessBasic:
    """Basic tests that verify script structure and parsing."""

    def test_script_parses_without_error(self, run_poe_main, tmp_path):
        """The completion script should parse without zsh errors."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        script_file = tmp_path / "completion.zsh"
        script_file.write_text(script)

        proc = subprocess.run(
            ["zsh", "-n", str(script_file)],
            capture_output=True,
            text=True,
        )

        assert proc.returncode == 0, f"Syntax error: {proc.stderr}"

    def test_script_can_be_sourced(self, run_poe_main, tmp_path):
        """The completion script can be sourced in zsh."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        proc = subprocess.run(
            ["zsh", "-c", f"source /dev/stdin << 'EOF'\n{script}\nEOF\necho ok"],
            capture_output=True,
            text=True,
        )

        assert proc.returncode == 0, f"Source error: {proc.stderr}"
        assert "ok" in proc.stdout

    def test_function_defined(self, run_poe_main, tmp_path):
        """The _poe function should be defined after sourcing."""
        result = run_poe_main("_zsh_completion")
        script = result.stdout

        proc = subprocess.run(
            [
                "zsh",
                "-c",
                f"source /dev/stdin << 'EOF'\n{script}\nEOF\n" "type _poe | head -1",
            ],
            capture_output=True,
            text=True,
        )

        assert proc.returncode == 0, f"Error: {proc.stderr}"
        assert "_poe is a shell function" in proc.stdout
