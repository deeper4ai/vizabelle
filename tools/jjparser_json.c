#define _GNU_SOURCE

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "DataTypes.h"
#include "Utilities.h"
#include "Examine.h"
#include "FileUtilities.h"
#include "List.h"
#include "Parsing.h"
#include "PrintTSTP.h"
#include "Signature.h"
#include "Tokenizer.h"

static void json_string(FILE *out, const char *s) {
    fputc('"', out);
    if (s != NULL) {
        for (const unsigned char *p = (const unsigned char *)s; *p != '\0'; p++) {
            switch (*p) {
                case '"':
                    fputs("\\\"", out);
                    break;
                case '\\':
                    fputs("\\\\", out);
                    break;
                case '\b':
                    fputs("\\b", out);
                    break;
                case '\f':
                    fputs("\\f", out);
                    break;
                case '\n':
                    fputs("\\n", out);
                    break;
                case '\r':
                    fputs("\\r", out);
                    break;
                case '\t':
                    fputs("\\t", out);
                    break;
                default:
                    if (*p < 0x20) {
                        fprintf(out, "\\u%04x", *p);
                    } else {
                        fputc(*p, out);
                    }
                    break;
            }
        }
    }
    fputc('"', out);
}

static char *formula_to_string(SyntaxType syntax, FORMULA formula) {
    char *buffer = NULL;
    size_t size = 0;
    FILE *stream = open_memstream(&buffer, &size);
    if (stream == NULL) {
        return NULL;
    }
    PrintTSTPFormula(stream, syntax, formula, 0, 0, outermost, 1);
    fclose(stream);
    return buffer;
}

static char *term_to_string(SyntaxType syntax, TERM term) {
    char *buffer = NULL;
    size_t size = 0;
    FILE *stream = open_memstream(&buffer, &size);
    if (stream == NULL) {
        return NULL;
    }
    PrintTSTPTerm(stream, syntax, term, 0, 0, 1);
    fclose(stream);
    return buffer;
}

static void print_string_array_from_lines(FILE *out, const char *lines) {
    fputc('[', out);
    if (lines != NULL && *lines != '\0') {
        char *copy = strdup(lines);
        char *saveptr = NULL;
        char *item = strtok_r(copy, "\n", &saveptr);
        int first = 1;
        while (item != NULL) {
            if (*item != '\0') {
                if (!first) {
                    fputc(',', out);
                }
                json_string(out, item);
                first = 0;
            }
            item = strtok_r(NULL, "\n", &saveptr);
        }
        free(copy);
    }
    fputc(']', out);
}

static void split_file_source(char *file_source, char **file, char **node) {
    *file = NULL;
    *node = NULL;
    if (file_source == NULL) {
        return;
    }
    char *newline = strchr(file_source, '\n');
    if (newline == NULL) {
        *file = file_source;
        return;
    }
    *newline = '\0';
    *file = file_source;
    *node = newline + 1;
}

static void print_nullable_string_field(FILE *out, const char *name, const char *value) {
    fprintf(out, ",\"%s\":", name);
    if (value == NULL) {
        fputs("null", out);
    } else {
        json_string(out, value);
    }
}

static void print_term_json(FILE *out, SyntaxType syntax, TERM term);
static void print_formula_json(FILE *out, SyntaxType syntax, FORMULA formula);

static void print_formula_array_json(FILE *out, SyntaxType syntax, int count, FORMULAArray formulae) {
    fputc('[', out);
    for (int index = 0; index < count; index++) {
        if (index > 0) {
            fputc(',', out);
        }
        print_formula_json(out, syntax, formulae[index]);
    }
    fputc(']', out);
}

static void print_term_args_json(FILE *out, SyntaxType syntax, TERM term) {
    int arity = GetArity(term);
    TERMArray arguments = GetArguments(term);
    fputs(",\"args\":[", out);
    for (int index = 0; index < arity && arguments != NULL; index++) {
        if (index > 0) {
            fputc(',', out);
        }
        print_term_json(out, syntax, arguments[index]);
    }
    fputc(']', out);
}

static void print_term_json(FILE *out, SyntaxType syntax, TERM term) {
    if (term == NULL) {
        fputs("null", out);
        return;
    }

    fputc('{', out);
    fputs("\"kind\":\"term\",\"type\":", out);
    json_string(out, TermTypeToString(term->Type));
    fputs(",\"symbol\":", out);
    json_string(out, GetSymbol(term));
    print_term_args_json(out, syntax, term);
    if (term->Type == formula && term->TheSymbol.Formula != NULL) {
        fputs(",\"formula\":", out);
        print_formula_json(out, syntax, term->TheSymbol.Formula);
    }
    fputc('}', out);
}

static void print_formula_json(FILE *out, SyntaxType syntax, FORMULA formula) {
    if (formula == NULL) {
        fputs("null", out);
        return;
    }

    fputc('{', out);
    fputs("\"kind\":", out);
    json_string(out, FormulaTypeToString(formula->Type));
    switch (formula->Type) {
        case quantified:
            fputs(",\"quantifier\":", out);
            json_string(out, ConnectiveToString(formula->FormulaUnion.QuantifiedFormula.Quantifier));
            fputs(",\"variable\":", out);
            print_term_json(out, syntax, formula->FormulaUnion.QuantifiedFormula.Variable);
            if (formula->FormulaUnion.QuantifiedFormula.VariableType != NULL) {
                fputs(",\"variable_type\":", out);
                print_formula_json(out, syntax, formula->FormulaUnion.QuantifiedFormula.VariableType);
            }
            fputs(",\"body\":", out);
            print_formula_json(out, syntax, formula->FormulaUnion.QuantifiedFormula.Formula);
            break;
        case binary:
        case assignment:
        case type_declaration:
            fputs(",\"connective\":", out);
            json_string(out, ConnectiveToString(formula->FormulaUnion.BinaryFormula.Connective));
            fputs(",\"lhs\":", out);
            print_formula_json(out, syntax, formula->FormulaUnion.BinaryFormula.LHS);
            fputs(",\"rhs\":", out);
            print_formula_json(out, syntax, formula->FormulaUnion.BinaryFormula.RHS);
            break;
        case unary:
            fputs(",\"connective\":", out);
            json_string(out, ConnectiveToString(formula->FormulaUnion.UnaryFormula.Connective));
            fputs(",\"body\":", out);
            print_formula_json(out, syntax, formula->FormulaUnion.UnaryFormula.Formula);
            break;
        case atom:
        case applied_connective:
            fputs(",\"atom\":", out);
            print_term_json(out, syntax, formula->FormulaUnion.Atom);
            break;
        case tuple:
            fprintf(out, ",\"opening\":");
            json_string(out, (char[]){formula->FormulaUnion.TupleFormula.OpeningBracket, '\0'});
            fputs(",\"elements\":", out);
            print_formula_array_json(
                out,
                syntax,
                formula->FormulaUnion.TupleFormula.NumberOfElements,
                formula->FormulaUnion.TupleFormula.Elements
            );
            break;
        case sequent:
            fputs(",\"lhs\":", out);
            print_formula_array_json(
                out,
                syntax,
                formula->FormulaUnion.SequentFormula.NumberOfLHSElements,
                formula->FormulaUnion.SequentFormula.LHS
            );
            fputs(",\"rhs\":", out);
            print_formula_array_json(
                out,
                syntax,
                formula->FormulaUnion.SequentFormula.NumberOfRHSElements,
                formula->FormulaUnion.SequentFormula.RHS
            );
            break;
        case ite_formula:
            fputs(",\"condition\":", out);
            print_formula_json(out, syntax, formula->FormulaUnion.ConditionalFormula.Condition);
            fputs(",\"then\":", out);
            print_formula_json(out, syntax, formula->FormulaUnion.ConditionalFormula.FormulaIfTrue);
            fputs(",\"else\":", out);
            print_formula_json(out, syntax, formula->FormulaUnion.ConditionalFormula.FormulaIfFalse);
            break;
        case let_formula:
            fputs(",\"types\":", out);
            print_formula_json(out, syntax, formula->FormulaUnion.LetFormula.LetTypes);
            fputs(",\"definition\":", out);
            print_formula_json(out, syntax, formula->FormulaUnion.LetFormula.LetDefn);
            fputs(",\"body\":", out);
            print_formula_json(out, syntax, formula->FormulaUnion.LetFormula.LetBody);
            break;
        case nonformulatype:
            break;
    }
    fputc('}', out);
}

int main(void) {
    SIGNATURE signature = NewSignatureWithTypes();
    if (signature == NULL) {
        fputs("failed to create JJParser signature\n", stderr);
        return EXIT_FAILURE;
    }

    SetNeedForNonLogicTokens(0);
    SetAllowFreeVariables(1);
    SetWarnings(0);

    LISTNODE head = ParseFILEOfFormulae("--", stdin, signature, 0, NULL);
    for (LISTNODE node = head; node != NULL; node = node->Next) {
        ANNOTATEDFORMULA annotated = node->AnnotatedFormula;
        if (!LogicalAnnotatedFormula(annotated)) {
            continue;
        }

        AnnotatedTSTPFormulaType *tstp = GetAnnotatedTSTPFormula(annotated);
        SyntaxType syntax = GetSyntax(annotated);
        TERM substatus = NULL;
        StatusType role = GetRole(annotated, &substatus);

        char *formula = formula_to_string(syntax, tstp->FormulaWithVariables->Formula);
        char *source = tstp->Source == NULL ? NULL : term_to_string(syntax, tstp->Source);
        char *useful_info = tstp->UsefulInfo == NULL ? NULL : term_to_string(syntax, tstp->UsefulInfo);
        char *rule = GetInferenceRule(annotated, NULL);
        char *parents = GetNodeParentNames(annotated, 0, NULL);
        char *file_source = GetFileSourceNameAndNode(annotated, NULL);
        char *file = NULL;
        char *file_node = NULL;

        split_file_source(file_source, &file, &file_node);

        fputc('{', stdout);
        fputs("\"syntax\":", stdout);
        json_string(stdout, SyntaxToString(syntax));
        fputs(",\"name\":", stdout);
        json_string(stdout, tstp->Name);
        fputs(",\"role\":", stdout);
        json_string(stdout, StatusToString(role));
        fputs(",\"formula\":", stdout);
        json_string(stdout, formula);
        fputs(",\"formula_ast\":", stdout);
        print_formula_json(stdout, syntax, tstp->FormulaWithVariables->Formula);
        print_nullable_string_field(stdout, "source", source);
        print_nullable_string_field(stdout, "inference_rule", rule);
        fputs(",\"parents\":", stdout);
        print_string_array_from_lines(stdout, parents);
        print_nullable_string_field(stdout, "file", file);
        print_nullable_string_field(stdout, "file_node", file_node);
        print_nullable_string_field(stdout, "useful_info", useful_info);
        fputs("}\n", stdout);

        free(formula);
        free(source);
        free(useful_info);
        free(rule);
        free(parents);
        free(file_source);
    }

    FreeListOfAnnotatedFormulae(&head, signature);
    FreeSignature(&signature);
    return EXIT_SUCCESS;
}
