## Quick Reference

|           Types           |                                 SAS Code                                 |                                      Query Code                                      |
| :-----------------------: | :----------------------------------------------------------------------: | :----------------------------------------------------------------------------------: |
|   Arithmetic Operations   |                    `(variable_1 + variable_2) / 100`                     |                          `(variable_1 + variable_2) / 100`                           |
|   Comparison Operations   |                        `100 < variable_1 <= 200`                         |                               `100 < variable <= 200`                                |
|    Equality Operations    |        `variable_1 = variable_2` <br/> `variable_1 ne variable_2`        |             `variable_1 == variable_2` <br/> `variable_1 != variable_2`              |
|    Boolean Operations     |                         `(x < 100) or (y > 200)`                         |                               `(x < 100) or (y > 200)`                               |
| Variable name with space  |                          `"variable 1"n <= 300`                          |                               `` `variable 1` <= 300``                               |
|   Membership Check (in)   |                             `x in (1, 2, 3)`                             |     `x == [1, 2, 3]` or `x in (1, 2, 3)` or `x == (1, 2, 3)` or `x in [1, 2, 3]`     |
|   Membership Check (not in) |                           `x not in (1, 2, 3)`                           | `x != [1, 2, 3]` or `x not in (1, 2, 3)` or `x != (1, 2, 3)` or `x not in [1, 2, 3]` |
|   Comparison with Nulls   | `missing(variable)` or `"variable 1"n = .` <br/> `not missing(variable)` |       `variable.isna()` or `` `variable 1`.isna() `` <br/> `~variable.isna()`        |
|   String Contains         |                                  —                                       |                              `variable.contains('text')`                              |
|   String Starts With      |                                  —                                       |               `variable.startswith('text')` or `variable.starts_with('text')`         |
|   String Ends With        |                                  —                                       |                 `variable.endswith('text')` or `variable.ends_with('text')`           |

## Math Functions

The following math functions can be used in filter expressions. Each takes a single column argument and returns a transformed value for comparison.

| Function | Example | Description |
| :------: | :------ | :---------- |
| `abs`      | `abs(x) > 10`      | Absolute value |
| `sqrt`     | `sqrt(x) > 1.5`    | Square root |
| `exp`      | `exp(x) > 100`     | Exponential (e^x) |
| `expm1`    | `expm1(x) > 10`    | e^x − 1 |
| `log`      | `log(x) > 0`       | Natural logarithm (ln) |
| `log1p`    | `log1p(x) > 1`     | ln(1 + x) |
| `log10`    | `log10(x) > 2`     | Base-10 logarithm |
| `sin`      | `sin(x) > 0`       | Sine |
| `cos`      | `cos(x) < 0`       | Cosine |
| `tanh`     | `tanh(x) > 0.5`    | Hyperbolic tangent |
| `sinh`     | `sinh(x) > 1`      | Hyperbolic sine |
| `cosh`     | `cosh(x) > 1`      | Hyperbolic cosine |
| `arcsin`   | `arcsin(x) > 0`    | Inverse sine (domain: −1 to 1) |
| `arccos`   | `arccos(x) > 1`    | Inverse cosine (domain: −1 to 1) |
| `arctan`   | `arctan(x) > 0`    | Inverse tangent |
| `arcsinh`  | `arcsinh(x) > 0`   | Inverse hyperbolic sine |
| `arccosh`  | `arccosh(x) > 1`   | Inverse hyperbolic cosine (domain: ≥ 1) |
| `arctanh`  | `arctanh(x) > 0.5` | Inverse hyperbolic tangent (domain: −1 to 1) |
| `arctan2`  | `arctan2(y, x) > 0` | Two-argument arctangent |
