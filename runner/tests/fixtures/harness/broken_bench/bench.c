/* Deliberately broken harness fixture: used only to test that a failure at
 * the harness/link stage never gets attributed a student-code line number
 * (build_c calls _run_compiler with source_path=None for this stage). */
int main(void) { syntax error }
