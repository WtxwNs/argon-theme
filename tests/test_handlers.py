"""Focused PHP handler regressions using WordPress test doubles.

Run with: python3 -m unittest discover -s tests -v
Requires the PHP CLI. These checks complement, not replace, WordPress integration tests.
"""
import json
import pathlib
import shutil
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

PHP_BOOTSTRAP = r'''
function load_function($file, $name) {
    $tokens = token_get_all(file_get_contents($file));
    for ($i = 0; $i < count($tokens); $i++) {
        if (!is_array($tokens[$i]) || $tokens[$i][0] !== T_FUNCTION) continue;
        $j = $i + 1;
        while (is_array($tokens[$j]) && $tokens[$j][0] === T_WHITESPACE) $j++;
        if (!is_array($tokens[$j]) || $tokens[$j][1] !== $name) continue;
        $code = ''; $depth = 0; $started = false;
        for (; $i < count($tokens); $i++) {
            $token = $tokens[$i];
            $code .= is_array($token) ? $token[1] : $token;
            if ($token === '{') { $depth++; $started = true; }
            if ($token === '}' && --$depth === 0 && $started) { eval($code); return; }
        }
    }
    throw new Exception('Function not found: ' . $name);
}
$writes = array();
$capabilities = array();
$meta = array();
$comment = (object) array('comment_approved' => '1');
$visible = true; $owner = false; $history_access = 'everyone';
function current_user_can($cap, $id = null) { global $capabilities; return in_array($cap . ($id === null ? '' : ':' . $id), $capabilities, true); }
function wp_verify_nonce($nonce, $action) { return $nonce === 'valid'; }
function absint($value) { return abs(intval($value)); }
function wp_unslash($value) { return stripslashes($value); }
function wp_slash($value) { return addslashes($value); }
function wp_send_json($value, $status = null) { echo json_encode(array('response' => $value, 'http_status' => $status)); exit; }
function get_post_meta($id, $key, $single) { global $meta; return $meta[$key] ?? ''; }
function update_post_meta($id, $key, $value) { global $writes; $writes[] = array($id, $key, $value); return true; }
function wp_kses_post($value) { return 'filtered:' . $value; }
function wp_strip_all_tags($value) { return strip_tags($value); }
function get_comment($id) { global $comment; return $comment; }
function user_can_view_comment($id) { global $visible; return $visible; }
function check_comment_token($id) { global $owner; return $owner; }
function check_comment_userid($id) { global $owner; return $owner; }
function get_option($key) { global $history_access; return $history_access; }
function update_option($key, $value) { global $writes; $writes[] = array($key, $value); }
'''


@unittest.skipUnless(shutil.which('php'), 'PHP CLI is required')
class HandlerTests(unittest.TestCase):
    def run_php(self, function, body, file='functions.php'):
        script = PHP_BOOTSTRAP + '\nload_function(' + json.dumps(str(ROOT / file)) + ', ' + json.dumps(function) + ');\n' + body
        result = subprocess.run(['php', '-d', 'display_errors=stderr', '-r', script], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, '', result.stderr)
        return json.loads(result.stdout)

    def ajax(self, caps=(), key='argon_show_post_outdated_info', value='always', nonce='valid'):
        post = dict(argon_meta_box_nonce=nonce, post_id='42', meta_key=key, meta_value=value)
        return self.run_php('update_post_meta_ajax', '$capabilities = json_decode(' + json.dumps(json.dumps(list(caps))) + ', true); $_POST = json_decode(' + json.dumps(json.dumps(post)) + ', true); update_post_meta_ajax(); echo json_encode(null);')

    def test_ajax_requires_permission_for_target_post(self):
        for caps in ((), ('edit_post:7',)):
            self.assertEqual(self.ajax(caps)['http_status'], 403)

    def test_ajax_restricts_keys_and_values(self):
        for key, value in (('other_setting', 'always'), ('argon_show_post_outdated_info', 'unexpected')):
            self.assertEqual(self.ajax(('edit_post:42',), key, value)['http_status'], 400)

    def test_ajax_accepts_supported_values(self):
        for value in ('default', 'always', 'never'):
            self.assertEqual(self.ajax(('edit_post:42',), value=value), {'status': 'success'})

    def test_ajax_rejects_invalid_nonce(self):
        self.assertIsNone(self.ajax(('edit_post:42',), nonce='invalid'))

    def test_history_obeys_visibility_and_moderation(self):
        cases = [('$visible = false;', False), ('$comment = null;', False),
                 ("$comment->comment_approved = '0';", False),
                 ("$comment->comment_approved = '0'; $owner = true;", True),
                 ("$comment->comment_approved = '0'; $capabilities = array('moderate_comments');", True),
                 ('', True)]
        for setup, expected in cases:
            self.assertEqual(self.run_php('can_visit_comment_edit_history', setup + ' echo json_encode(can_visit_comment_edit_history(42));'), expected)

    def test_save_uses_target_permission_for_any_post_type(self):
        result = self.run_php('argon_save_meta_data', "$_POST = array('argon_meta_box_nonce' => 'valid', 'post_type' => 'custom'); argon_save_meta_data(42); echo json_encode($writes);")
        self.assertEqual(result, [])

    def test_save_respects_html_capability_and_preserves_slashes(self):
        data = dict(argon_meta_box_nonce='valid', post_type='post', argon_meta_hide_readingtime='false', argon_meta_simple='false', argon_first_image_as_thumbnail='default', argon_show_post_outdated_info='default', argon_after_post='<b>content</b>', argon_custom_css='p { color: red; }')
        for unrestricted in (False, True):
            caps = ['edit_post:42'] + (['unfiltered_html'] if unrestricted else [])
            body = '$capabilities = json_decode(' + json.dumps(json.dumps(caps)) + ', true); $_POST = json_decode(' + json.dumps(json.dumps(data)) + ', true); argon_save_meta_data(42); echo json_encode($writes);'
            writes = self.run_php('argon_save_meta_data', body)
            after_post = next(row[2] for row in writes if row[1] == 'argon_after_post')
            self.assertEqual(after_post, data['argon_after_post'] if unrestricted else 'filtered:' + data['argon_after_post'])

    def test_settings_require_administrator_capability(self):
        self.assertEqual(self.run_php('argon_update_themeoptions', "$_POST = array('update_themeoptions' => 'true', 'argon_update_themeoptions_nonce' => 'valid'); argon_update_themeoptions(); echo json_encode($writes);", 'settings.php'), [])

    def test_textareas_escape_saved_values(self):
        source = (ROOT / 'functions.php').read_text()
        self.assertIn('echo esc_textarea($argon_after_post);', source)
        self.assertIn('echo esc_textarea($argon_custom_css);', source)
        self.assertNotIn("add_action('wp_ajax_nopriv_update_post_meta_ajax'", source)


if __name__ == '__main__':
    unittest.main()
