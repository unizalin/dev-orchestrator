from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, mock
import contextlib, io, json, os
from dataclasses import dataclass

@dataclass
class CliResult:
    returncode:int; stdout:str; stderr:str

def run_cli(*args, state_dir):
    from scripts.dev_orchestrator_usage import cli
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.dict(os.environ, {'DEV_ORCHESTRATOR_STATE_DIR': str(state_dir)}, clear=False), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main(list(args))
    return CliResult(rc, out.getvalue(), err.getvalue())

class UsageCliTests(TestCase):
    def test_setup_is_required_before_recording(self):
        with TemporaryDirectory() as tmp:
            result = run_cli('task-start', state_dir=Path(tmp))
            self.assertEqual(result.returncode, 3)
            self.assertIn('tracking is not enabled', result.stderr)

    def test_setup_stores_alias_and_enables_tracking(self):
        with TemporaryDirectory() as tmp:
            result = run_cli('setup', '--account', 'personal', '--no-launcher', state_dir=Path(tmp))
            self.assertEqual(result.returncode, 0)
            self.assertIn('personal', result.stdout)

    def test_help_lists_commands(self):
        from scripts.dev_orchestrator_usage import cli
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(['--help']), 0)
        for name in ('setup','accounts','current','all','summary','task-start','checkpoint','finish','run-agy'):
            self.assertIn(name, out.getvalue())

    def test_summary_json_contract_and_diagnostics(self):
        from scripts.dev_orchestrator_usage.model import UsageEvent, TokenUsage
        from scripts.dev_orchestrator_usage.project import resolve_project
        from scripts.dev_orchestrator_usage.state import Ledger
        from datetime import datetime, timezone
        with TemporaryDirectory() as tmp:
            root = Path(tmp); run_cli('setup', '--account', 'personal', '--no-launcher', state_dir=root)
            project = resolve_project(Path.cwd()); now = datetime.now(timezone.utc)
            event = UsageEvent.new(started_at=now, completed_at=now, project_key=project.key,
                project_label=project.label, account_alias='personal', task_id='t', thread_id=None,
                session_id='s', conversation_id=None, role='implement', provider='x', model='m',
                source='x', precision='exact', usage=TokenUsage(1, 0, 0, 1, 0, 12))
            Ledger(root).append(event)
            (root / 'events' / 'bad.jsonl').write_text('{bad json}\n', encoding='utf-8')
            result = run_cli('summary', '--scope', 'all_projects', '--window', '5h', state_dir=root)
            self.assertEqual(result.returncode, 0); self.assertEqual(result.stderr, '')
            payload = json.loads(result.stdout)
            self.assertEqual(payload['schema_version'], 1)
            self.assertEqual(payload['scope'], 'all_projects')
            self.assertEqual(payload['all_projects_window_total'], 12)
            self.assertEqual(payload['diagnostics']['malformed_event_count'], 1)
            self.assertNotIn('prompt', result.stdout.lower()); self.assertNotIn('response', result.stdout.lower())

    def test_summary_disabled_and_invalid_arguments(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            disabled = run_cli('summary', state_dir=root)
            self.assertEqual(disabled.returncode, 3)
            self.assertIn('tracking is not enabled', disabled.stderr)
            run_cli('setup', '--account', 'personal', '--no-launcher', state_dir=root)
            invalid_window = run_cli('summary', '--window', 'bad', state_dir=root)
            self.assertEqual(invalid_window.returncode, 2)
            self.assertIn('window', invalid_window.stderr.lower())
            invalid_scope = run_cli('summary', '--scope', 'bad', state_dir=root)
            self.assertEqual(invalid_scope.returncode, 2)
            self.assertIn('invalid choice', invalid_scope.stderr.lower())

    def test_summary_project_path_override_changes_current_project_only(self):
        from datetime import datetime, timezone
        from scripts.dev_orchestrator_usage.model import UsageEvent, TokenUsage
        from scripts.dev_orchestrator_usage.project import resolve_project
        from scripts.dev_orchestrator_usage.state import Ledger

        with TemporaryDirectory() as tmp, TemporaryDirectory() as override_dir:
            root = Path(tmp)
            override = Path(override_dir)
            run_cli('setup', '--account', 'personal', '--no-launcher', state_dir=root)
            current = resolve_project(Path.cwd())
            overridden = resolve_project(override)
            now = datetime.now(timezone.utc)

            def event(project, total):
                return UsageEvent.new(
                    started_at=now, completed_at=now, project_key=project.key,
                    project_label=project.label, account_alias='personal',
                    task_id=project.label, thread_id=None, session_id=project.label,
                    conversation_id=None, role='r', provider='x', model='m',
                    source='x', precision='exact',
                    usage=TokenUsage(1, 0, 0, 1, 0, total),
                )

            Ledger(root).append(event(current, 3))
            Ledger(root).append(event(overridden, 7))
            result = run_cli(
                'summary', '--scope', 'current_project', '--window', '5h',
                '--project-path', str(override), state_dir=root,
            )
            self.assertEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload['current_project']['key'], overridden.key)
            self.assertEqual(payload['selected_scope_window_total'], 7)
            self.assertEqual(payload['all_projects_window_total'], 10)

    def test_summary_account_filter_does_not_change_active_account(self):
        from scripts.dev_orchestrator_usage.model import UsageEvent, TokenUsage
        from scripts.dev_orchestrator_usage.project import resolve_project
        from scripts.dev_orchestrator_usage.state import AccountRegistry, Ledger
        from datetime import datetime, timezone
        with TemporaryDirectory() as tmp:
            root = Path(tmp); run_cli('setup', '--account', 'personal', '--no-launcher', state_dir=root)
            project = resolve_project(Path.cwd()); now = datetime.now(timezone.utc)
            for alias, total in (('personal', 3), ('work', 5)):
                Ledger(root).append(UsageEvent.new(started_at=now, completed_at=now, project_key=project.key,
                    project_label=project.label, account_alias=alias, task_id=alias, thread_id=None,
                    session_id=alias, conversation_id=None, role='r', provider='x', model='m', source='x',
                    precision='exact', usage=TokenUsage(1, 0, 0, 1, 0, total)))
            payload = json.loads(run_cli('summary', '--scope', 'all_projects', '--account', 'work', state_dir=root).stdout)
            self.assertEqual(payload['selected_scope_window_total'], 5)
            self.assertEqual(payload['all_projects_window_total'], 8)
            self.assertEqual(payload['active_account'], 'personal')
            self.assertEqual(AccountRegistry(root).active(), 'personal')

    def test_summary_without_account_filter_includes_all_accounts(self):
        from scripts.dev_orchestrator_usage.model import UsageEvent, TokenUsage
        from scripts.dev_orchestrator_usage.project import resolve_project
        from scripts.dev_orchestrator_usage.state import Ledger
        from datetime import datetime, timezone

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_cli('setup', '--account', 'personal', '--no-launcher', state_dir=root)
            project = resolve_project(Path.cwd())
            now = datetime.now(timezone.utc)
            for alias, total in (('personal', 3), ('work', 5)):
                Ledger(root).append(UsageEvent.new(
                    started_at=now,
                    completed_at=now,
                    project_key=project.key,
                    project_label=project.label,
                    account_alias=alias,
                    task_id=alias,
                    thread_id=None,
                    session_id=alias,
                    conversation_id=None,
                    role='implement',
                    provider='openai',
                    model='luna',
                    source='test',
                    precision='exact',
                    usage=TokenUsage(1, 0, 0, 1, 0, total),
                ))

            all_accounts = json.loads(run_cli(
                'summary', '--scope', 'current_project', state_dir=root
            ).stdout)
            self.assertEqual(all_accounts['selected_account'], None)
            self.assertEqual(all_accounts['selected_scope_window_total'], 8)
            self.assertEqual(all_accounts['current_project_cumulative_total'], 8)
            self.assertEqual(
                {(row['account_alias'], row['usage']['total_tokens']) for row in all_accounts['rows']},
                {('personal', 3), ('work', 5)},
            )

            work_only = json.loads(run_cli(
                'summary', '--scope', 'current_project', '--account', 'work', state_dir=root
            ).stdout)
            self.assertEqual(work_only['selected_account'], 'work')
            self.assertEqual(work_only['selected_scope_window_total'], 5)
            self.assertEqual(work_only['current_project_cumulative_total'], 5)
            self.assertEqual(work_only['all_projects_window_total'], 8)
            self.assertEqual(
                {(row['account_alias'], row['usage']['total_tokens']) for row in work_only['rows']},
                {('work', 5)},
            )

    def test_run_agy_uses_context_and_appends_event(self):
        from scripts.dev_orchestrator_usage import cli
        from scripts.dev_orchestrator_usage.state import AccountRegistry, Ledger
        from scripts.dev_orchestrator_usage.model import TokenUsage, UsageEvent
        from datetime import datetime, timezone
        with TemporaryDirectory() as tmp:
            root = Path(tmp); run_cli('setup', '--account', 'personal', '--no-launcher', state_dir=root)
            prompt = root / 'p.txt'; prompt.write_text('review')
            event = UsageEvent.new(started_at=datetime.now(timezone.utc), completed_at=datetime.now(timezone.utc), project_key='x', project_label='x', account_alias='personal', task_id='t', thread_id=None, session_id='s', conversation_id=None, role='investigate', provider='google', model='gemini-3.1-pro-high', source='agy', precision='exact', usage=TokenUsage(1,0,0,2,0,3))
            with mock.patch.object(cli, 'run_agy', return_value=('review complete\n', event)) as agy:
                result = run_cli('run-agy', '--role', 'investigate', '--model', 'gemini-3.1-pro-high', '--prompt-file', str(prompt), state_dir=root)
            self.assertEqual(result.returncode, 0); self.assertEqual(result.stdout, 'review complete\n'); self.assertNotIn('input_tokens', result.stdout); agy.assert_called_once()
            kwargs = agy.call_args.kwargs['context']; self.assertEqual(kwargs.role, 'investigate'); self.assertEqual(kwargs.model, 'gemini-3.1-pro-high'); self.assertEqual(kwargs.account_alias, 'personal')
            self.assertEqual(agy.call_args.kwargs['effort'], 'high')
            events = list(Ledger(root).events()); self.assertEqual(len(events), 1); self.assertEqual(events[0].usage.total_tokens, 3); self.assertEqual(events[0].role, 'investigate')

    def test_run_agy_cli_passes_auto_effort_for_model_specific_defaults(self):
        from scripts.dev_orchestrator_usage import cli
        from scripts.dev_orchestrator_usage.model import TokenUsage, UsageEvent
        from scripts.dev_orchestrator_usage.state import Ledger
        from datetime import datetime, timezone

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_cli('setup', '--account', 'personal', '--no-launcher', state_dir=root)
            prompt = root / 'p.txt'
            prompt.write_text('independent review')
            event = UsageEvent.new(
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
                project_key='x', project_label='x', account_alias='personal',
                task_id='t', thread_id=None, session_id='s', conversation_id=None,
                role='independent_review', provider='google', model='claude-sonnet-4-6',
                source='agy', precision='exact', usage=TokenUsage(1, 0, 0, 2, 0, 3),
            )
            with mock.patch.object(cli, 'run_agy', return_value=('review complete\n', event)) as agy:
                result = run_cli(
                    'run-agy', '--role', 'independent_review',
                    '--model', 'claude-sonnet-4-6', '--effort', 'auto',
                    '--prompt-file', str(prompt), state_dir=root,
                )

            self.assertEqual(result.returncode, 0)
            self.assertEqual(agy.call_args.kwargs['effort'], 'auto')
            self.assertEqual(len(list(Ledger(root).events())), 1)

    def test_current_filters_project_key_not_label(self):
        from scripts.dev_orchestrator_usage.model import UsageEvent, TokenUsage
        from scripts.dev_orchestrator_usage.state import Ledger
        from datetime import datetime, timezone
        with TemporaryDirectory() as tmp:
            root=Path(tmp); run_cli('setup','--account','personal','--no-launcher',state_dir=root)
            from scripts.dev_orchestrator_usage.project import resolve_project
            current_project = resolve_project(Path.cwd())
            now=datetime.now(timezone.utc)
            def event(key,total,label=current_project.label):
                return UsageEvent.new(started_at=now,completed_at=now,project_key=key,project_label=label,account_alias='personal',task_id=key,thread_id=None,session_id=key,conversation_id=None,role='implement',provider='x',model='m',source='x',precision='exact',usage=TokenUsage(1,0,0,1,0,total))
            Ledger(root).append(event(current_project.key, 2)); Ledger(root).append(event('other', 999))
            result=run_cli('current','--window','5h','--no-quota',state_dir=root)
            self.assertIn('TOTAL', result.stdout); self.assertIn('2', result.stdout); self.assertNotIn('999', result.stdout)

    def test_launcher_modes_and_invalid_accounts(self):
        with TemporaryDirectory() as tmp, TemporaryDirectory() as bindir:
            root=Path(tmp)
            self.assertEqual(run_cli('setup','--account','personal','--no-launcher',state_dir=root).returncode,0)
            self.assertFalse((Path(bindir)/'dev-orchestrator-usage').exists())
            with mock.patch.dict(os.environ, {'DEV_ORCHESTRATOR_BIN_DIR':bindir}, clear=False):
                self.assertEqual(run_cli('setup','--account','personal','--install-launcher',state_dir=root).returncode,0)
            self.assertTrue((Path(bindir)/'dev-orchestrator-usage').is_symlink())
            Path(bindir,'dev-orchestrator-usage').unlink(); Path(bindir,'dev-orchestrator-usage').write_text('keep')
            with mock.patch.dict(os.environ, {'DEV_ORCHESTRATOR_BIN_DIR':bindir}, clear=False):
                self.assertEqual(run_cli('setup','--account','personal','--install-launcher',state_dir=root).returncode,2)
            self.assertEqual(Path(bindir,'dev-orchestrator-usage').read_text(),'keep')
            self.assertEqual(run_cli('accounts','set','bad@x',state_dir=root).returncode,2)
            self.assertEqual(run_cli('setup','--account','x','--install-launcher','--no-launcher',state_dir=root).returncode,2)

    def test_quota_is_optional_and_keeps_accounts_separate(self):
        from scripts.dev_orchestrator_usage import cli
        from scripts.dev_orchestrator_usage.tokscale import QuotaResult, AccountQuota, QuotaWindow
        with TemporaryDirectory() as tmp:
            root=Path(tmp); run_cli('setup','--account','personal','--no-launcher',state_dir=root)
            quota=QuotaResult(True, (AccountQuota('p','personal',QuotaWindow(10,None),QuotaWindow(20,None)), AccountQuota('p','work',QuotaWindow(30,None),QuotaWindow(40,None))))
            with mock.patch.object(cli, 'load_quotas', return_value=quota) as load:
                result=run_cli('all',state_dir=root)
                self.assertIn('QUOTA personal', result.stdout); self.assertIn('QUOTA work', result.stdout); load.assert_called_once()
                result=run_cli('all','--no-quota',state_dir=root)
                self.assertNotIn('QUOTA', result.stdout)
                result=run_cli('all','--account','personal',state_dir=root)
                self.assertIn('QUOTA personal', result.stdout); self.assertNotIn('QUOTA work', result.stdout)

    def test_all_recording_commands_require_setup(self):
        with TemporaryDirectory() as tmp:
            for command in ('task-start','checkpoint','finish','run-agy'):
                args = [command]
                if command == 'run-agy': args += ['--role','r','--model','m','--prompt-file',str(Path(tmp)/'p')]
                result = run_cli(*args, state_dir=Path(tmp))
                self.assertEqual(result.returncode, 3, command)

    def test_lifecycle_missing_state_is_non_blocking(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp); run_cli('setup','--account','personal','--no-launcher',state_dir=root)
            with mock.patch.dict(os.environ, {'CODEX_HOME': str(root/'no-codex')}, clear=False):
                result=run_cli('task-start',state_dir=root)
            self.assertEqual(result.returncode,4); self.assertIn('task-start',result.stderr)
            result=run_cli('checkpoint','--task-id','missing',state_dir=root); self.assertEqual(result.returncode,4); self.assertIn('checkpoint',result.stderr)

    def test_help_does_not_create_state_path(self):
        with TemporaryDirectory() as tmp:
            missing=Path(tmp)/'missing'
            self.assertEqual(run_cli('--help',state_dir=missing).returncode,0)
            self.assertFalse(missing.exists())

    def test_accounts_switch_marks_only_active_and_preserves_history(self):
        from scripts.dev_orchestrator_usage.model import UsageEvent, TokenUsage
        from scripts.dev_orchestrator_usage.state import Ledger
        from datetime import datetime, timezone
        with TemporaryDirectory() as tmp:
            root=Path(tmp); run_cli('setup','--account','personal','--no-launcher',state_dir=root)
            now=datetime.now(timezone.utc)
            event=UsageEvent.new(started_at=now,completed_at=now,project_key='p',project_label='p',account_alias='personal',task_id='t',thread_id=None,session_id='s',conversation_id=None,role='r',provider='x',model='m',source='x',precision='exact',usage=TokenUsage(1,0,0,1,0,2))
            Ledger(root).append(event); run_cli('accounts','set','work',state_dir=root)
            result=run_cli('accounts',state_dir=root); self.assertIn('* work',result.stdout); self.assertIn('  personal',result.stdout)
            self.assertEqual(list(Ledger(root).events())[0].account_alias,'personal')
            fresh=Path(tmp)/'fresh'; self.assertEqual(run_cli('accounts','set','work',state_dir=fresh).returncode,3); self.assertFalse(fresh.exists())

    def test_quota_none_is_na_without_percent(self):
        from scripts.dev_orchestrator_usage import cli
        from scripts.dev_orchestrator_usage.tokscale import QuotaResult, AccountQuota, QuotaWindow
        with TemporaryDirectory() as tmp:
            root=Path(tmp); run_cli('setup','--account','personal','--no-launcher',state_dir=root)
            q=QuotaResult(True,(AccountQuota('p','personal',QuotaWindow(None,None),QuotaWindow(None,None)),))
            with mock.patch.object(cli,'load_quotas',return_value=q):
                out=run_cli('all',state_dir=root).stdout
            self.assertIn('SESSION N/A WEEKLY N/A',out); self.assertNotIn('N/A%',out)
