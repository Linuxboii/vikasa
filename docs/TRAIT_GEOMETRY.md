# Inherited trait geometry

Ordinary exports include hashed `trait-space.json`: configured bounds, living
creature IDs, birth ticks, generations, raw traits, normalized histograms,
covariance, correlations, PCA loadings, scores and variance fractions. Scores
retain individual row order. Measurements run only on export, not in the tick
loop, and consume no engine RNG. `run` and `batch` also render `trait_space.png`
alongside the existing four figures. This is not a new live Godot tab.

## Copy-paste commands

From the repository root on Windows:

```powershell
.\.venv\Scripts\vikasa.exe run --scenario experiments\baseline.json --output exports\trait-snapshot --seed 2026 --ticks 800
```

On macOS/Linux:

```bash
.venv/bin/vikasa run --scenario experiments/baseline.json --output exports/trait-snapshot --seed 2026 --ticks 800
```

These commands use baseline settings. The README illustration instead uses
`config/showcase.json`, seed 2026, tick 800: 157 living individuals, deepest
living generation 5. It is one illustration, not replicated evidence.

## Mathematics

For fixed configured bounds `a_j,b_j`:

```text
x_ij = (z_ij - a_j) / (b_j - a_j)
C = (X - mean(X))ᵀ (X - mean(X)) / (n - 1)
R_ij = C_ij / (sqrt(C_ii) sqrt(C_jj))
C v_k = lambda_k v_k
f_k = lambda_k / sum(lambda)
D_eff = 1 / sum(f_k²)
```

Fixed spans give unit invariance without forcing equal variance. `C` is sample
covariance, **not** additive genetic G. `D_eff` is the participation ratio (one
direction to six equally variable directions), neither heritability nor genetic
complexity. Solver: [NumPy `eigh`](https://numpy.org/doc/stable/reference/generated/numpy.linalg.eigh.html).

Covariance/PCA are unavailable below two individuals. Constant columns have
undefined correlations. If all traits are constant, variance fractions and
dimension are undefined, not zero. Reference-offset centering preserves exact
zero for identical decimals. Separate standard deviations and normalized
eigenvalue fractions avoid squared-product underflow; float64 resolution still
limits extremely small variation. Nonfinite/out-of-bounds clouds and nonfinite
bound spans are rejected.

Loadings are eigenvector columns in descending variance order; signs make the
largest-magnitude loading positive. Repeated positive eigenvalues are flagged:
tied axes have no unique orientation. Each snapshot fits its own PCA basis;
connecting those coordinates across time is not an evolutionary trajectory.
A fixed reference basis would be needed.

Survival, reproduction, environment, drift and inheritance affect distributions.
Correlation or generation clustering does not establish causal selection,
adaptation or heritability. Multilocus/diploid inheritance, dominance, plasticity
and controlled mechanism tests remain future work.
