# Historical Sample-Data Provenance (Not Redistributed Publicly)

This document records the identity of the 18 synthetic patient files used
during MEVA's internal development (Stages 3 through 8A) — for
transparency and historical traceability only. **These files are not part
of the public release** (as of Stage 8A.1) and are not present in
`data/synthetic/synthea/` going forward.

## Why these files were removed from the public dataset

These 18 files were downloaded from `synthetichealth/synthea-sample-data`
(`downloads/synthea_sample_data_fhir_r4_nov2021.zip`) — a repository
separate from the official Synthea generator, which currently has **no
declared license** (confirmed via that repository's own metadata: `license:
null`). See `THIRD_PARTY_NOTICES.md` for the full licensing analysis.

Rather than publicly redistribute files whose redistribution terms are
unclear, Stage 8A.1 generated a **new** set of synthetic patients locally,
directly from the official Apache-2.0-licensed Synthea generator (see
`data/synthetic/synthea/PROVENANCE.md`), and the public dataset now uses
only those newly generated files.

## What this means for historical results

**All Stage 3 through Stage 8A benchmark results (v0.1, v0.2, v0.3, and
every comparison/extraction/audit report built on them) were produced using
these 18 now-removed files.** Those results remain valid as a record of
what was measured, when, and how — they are not rewritten, deleted, or
reattributed. They should be read as **historical development artifacts**
based on the former sample-data fixtures, not as results on the new public
v0.4 dataset. See `docs/baseline-results-v0.3.md` for the full v0.3 report,
now explicitly labeled as historical.

The raw JSON result files referencing these patients remain in this
repository's local, gitignored `results/` directory — untouched by this
stage, not deleted, and not publicly redistributed either way (since
`results/` was never part of the public dataset).

## Removed file identity (no copyrighted content included below — filenames and hashes only)

| Repo filename (removed) | Original `synthea-sample-data` filename | SHA-256 of the removed file |
|---|---|---|
| `patient-01.json` | `Juliette736_McClure239_363f50e2-9771-dfb4-1ff5-3d7db24b9ada.json` | `683764ac99c03a00fd6459571612170d459d819f069363db1d07620124935b33` |
| `patient-02.json` | `Nathanial472_Beatty507_c28b00a3-54c0-21ba-4ed7-de871f1b157f.json` | `fd0a74d3e49aca0abb61294b4c0357e7dc6fe9a6867cc620cab4caa7c323ac91` |
| `patient-03.json` | `Alicia629_Jakubowski832_6895f047-ab31-c293-b335-374256e01eb1.json` | `0f0412e478e4a35b120d1a398698fde3433f3649e2057d3adcd98a033949bb08` |
| `patient-04.json` | `Andrea7_Champlin946_a57b5df9-090b-3367-e302-89f6c9660923.json` | `b809cc259b9b0527a127a2d487fb1af2455d7c3b7b157a28a5f6a9d901258c8e` |
| `patient-05.json` | `Brandon214_Watsica258_faac724a-a9e9-be66-fe1e-3044dc0ba8ea.json` | `1219eb60428f711300c340407318b9b5fe3a7d206bf73f1265290cc2d4d67a13` |
| `patient-06.json` | `Buddy254_Gislason620_e4c43a21-11b3-d96d-ede9-0c71e8cb1574.json` | `ce30ba440d25f1b1058f1a781068e6b72a4dca69d2d3da5a8783304f48141eb3` |
| `patient-07.json` | `Charlsie105_Jacobson885_fab540db-3bc8-bbf8-69bc-5d8a9dbb752f.json` | `5eceee9e1fb527e842e5247e37959aa344b21724ca48e3381c539e1c73180433` |
| `patient-08.json` | `Eli762_Douglas31_7d5e31d3-163b-4a77-576b-1ed21adf8c09.json` | `fa5511a6c72efc34be8ee3b3d5d502bd786263f147c079abda0f127167ddd22c` |
| `patient-09.json` | `Francisco472_Stracke611_ce032ded-978b-b56b-425f-5159d4a4038e.json` | `ddc059487134d0064f55b01716ae635a4b04d50112097ef27ea181130491cc2f` |
| `patient-10.json` | `Harland508_Price929_d8e3a701-d108-74ff-2ce3-156537276a14.json` | `f2b64687f4d8855884f5c64d71bfa444119698ded093e78de5bb934827d58acd` |
| `patient-11.json` | `Harris789_Torphy630_251ec304-b5fb-e3fa-72ed-197b957c3378.json` | `b80933d813ecd7ec0ace9c28d1ae89c03b41593e82d8dee56c939198979530c8` |
| `patient-12.json` | `Hassan290_Wyman904_b1b0fe43-a0f7-3ea6-67f8-0b5a3afd5a8e.json` | `265cfa4445ce52fd9a9fcd76e0ecdec6850311853561a8b1ac0e5ddc30ae0334` |
| `patient-13.json` | `Isaac321_Marks830_2c622c62-af49-25e3-4f67-3ab19a455bb2.json` | `91a0992ad9ff5a319077c37f5b74a16177f7ad046124a15eab25e6de781b4691` |
| `patient-14.json` | `Jolynn62_Conn188_2798ae24-ef3b-1906-6e41-a31e0fd833a0.json` | `049054c83880f55e7a3dd565f7f98eb77794b347da91e35f80cf23e44cb8a637` |
| `patient-15.json` | `Miguel815_Braun514_d1f767cc-a980-8bd9-8a1b-f7ada327b40c.json` | `f246bc0a77bbd07a3d130638170689bf43e02cd008334f31001a4e9c446abd4a` |
| `patient-16.json` | `Pam996_Kris249_423a9252-21e3-6141-4207-46a9066fd7f4.json` | `f88f947bf59f970f8ea96c1d490f959218c691537f85641d9e720831b1fc20d8` |
| `patient-17.json` | `Raymonde315_Marvin195_b3c96d58-b033-6bc7-a65f-3acd85698fd6.json` | `d7bda614004f25431ffcacb52190f605563a4e7295edbddeba9d1e165b2e6d1b` |
| `patient-18.json` | `Vennie613_Hermiston71_f4018f25-2220-b846-1dea-5d0818e0baea.json` | `71e9b407182b25b76fccfa92ce147184a7ecf49d2040555d9d52fa6f3fcbbf58` |

No file content, patient names, or medical data from these files is
reproduced above — only filenames and content hashes, recorded for
traceability. All 18 patients were, in any case, entirely fictional
(Synthea-generated), never real individuals.

## Source archive

`synthetichealth/synthea-sample-data`, file
`downloads/synthea_sample_data_fhir_r4_nov2021.zip` (see prior
`docs/synthetic-data.md` history for the original download context).
