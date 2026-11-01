from app.experiments import prepare_units

STARTER = '#define GAP_BYTES 0 // spacing\nint main(void) { return GAP_BYTES; }\n'


def test_arbitrary_code_and_c_expression_allowed():
    code = STARTER.replace('0 // spacing', '(8ULL << 20)').replace('return GAP_BYTES', 'return 42')
    units, label = prepare_units(STARTER, code)
    assert label == '(8ULL << 20)'
    assert units['b'].startswith(code)
    assert units['a'].startswith(STARTER)


def test_missing_macro_is_left_to_compiler():
    units, label = prepare_units(STARTER, 'invalid C')
    assert label is None
    assert units['b'].startswith('invalid C')
