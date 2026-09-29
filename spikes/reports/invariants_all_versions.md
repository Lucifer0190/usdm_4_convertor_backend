# Invariants over 204 protocols (0 crashed)

## slots

| Invariant | Holds | Rate |
|---|---:|---:|
| design | 204/204 | 100% |
| exclusion | 204/204 | 100% |
| inclusion | 204/204 | 100% |
| interventions | 204/204 | 100% |
| objectives | 204/204 | 100% |
| soa | 204/204 | 100% |
| synopsis | 204/204 | 100% |

## soa

| Invariant | Holds | Rate |
|---|---:|---:|
| activity_names_are_label_sized | 200/204 | 98% |
| enough_visits_and_activities | 202/204 | 99% |
| every_visit_has_a_mark | 127/204 | 62% |
| every_visit_has_an_epoch | 199/204 | 98% |
| grid_found | 202/204 | 99% |
| marks_are_in_range | 202/204 | 99% |
| most_activities_are_scheduled | 194/204 | 95% |
| slot_found | 204/204 | 100% |
| visit_names_are_real | 195/204 | 96% |
| visit_names_are_unique_enough | 125/204 | 61% |

## eligibility

| Invariant | Holds | Rate |
|---|---:|---:|
| has_exclusion | 190/204 | 93% |
| has_inclusion | 185/204 | 91% |
| items_are_criterion_sized | 177/204 | 87% |
| list_sizes_are_plausible | 185/204 | 91% |

## objectives

| Invariant | Holds | Rate |
|---|---:|---:|
| every_row_has_an_endpoint | 180/204 | 88% |
| has_a_primary_objective | 190/204 | 93% |
| objective_text_is_real | 183/204 | 90% |
| table_found | 201/204 | 99% |

## Protocols failing at least one SoA invariant

- B7981032 / Clinical Protocol - 0 (03Apr2019).pdf: every_visit_has_a_mark, most_activities_are_scheduled  {'method': 'geometry', 'visits': 14, 'activities': 66, 'marks': 287}
- C1071003 / Clinical Protocol - 0 (03Aug2022).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 20, 'activities': 88, 'marks': 266}
- C2321014 / Clinical Protocol - 0 (03May2024).pdf: every_visit_has_a_mark, visit_names_are_real, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 47, 'activities': 43, 'marks': 263}
- C4221026 / Clinical Protocol - 0 (03Nov2021) 2.pdf: grid_found, enough_visits_and_activities  None
- C3671013 / Clinical Protocol - 0 (07Jul2021).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 8, 'activities': 35, 'marks': 46}
- C4891026 / Clinical Protocol - 0 (12Sep2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 67, 'activities': 47, 'marks': 270}
- C4221016 / Clinical Protocol - 0 (13Oct2020).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 20, 'activities': 51, 'marks': 164}
- C4891006 / Clinical Protocol - 0 (14Jun2022).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 30, 'activities': 41, 'marks': 155}
- C4891023 / Clinical Protocol - 0 (14Jun2022).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 79, 'activities': 45, 'marks': 299}
- C2321003 / Clinical Protocol - 0 (14Jun2024).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 72, 'activities': 40, 'marks': 227}
- C4221015 / Clinical Protocol - 0 (15Jul2020).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 24, 'activities': 60, 'marks': 268}
- C4891001 / Clinical Protocol - 0 (15Jun2022).pdf: every_visit_has_a_mark, visit_names_are_real, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 39, 'activities': 46, 'marks': 165}
- B7981118 / Clinical Protocol - 0 (16Jul2025).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 20, 'activities': 57, 'marks': 302}
- C4891024 / Clinical Protocol - 0 (22Jun2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 151, 'activities': 56, 'marks': 418}
- C1071006 / Clinical Protocol - 0 (26May2022).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 37, 'activities': 79, 'marks': 280}
- B7981119 / Clinical Protocol - 0 (28Jul2025).pdf: every_visit_has_an_epoch, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 21, 'activities': 50, 'marks': 238}
- B7981080 / Clinical Protocol - 0 (28Jun2023).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 30, 'activities': 70, 'marks': 677}
- C1071007 / Clinical Protocol - 0 (29Nov2021).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 22, 'activities': 64, 'marks': 148}
- C4891024 / Clinical Protocol - 1 (02Feb2024).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 151, 'activities': 56, 'marks': 418}
- C1071006 / Clinical Protocol - 1 (03Aug2022).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 20, 'activities': 88, 'marks': 266}
- C1071007 / Clinical Protocol - 1 (04May2022).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 22, 'activities': 61, 'marks': 149}
- C4221015 / Clinical Protocol - 1 (07Aug2020).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 24, 'activities': 61, 'marks': 269}
- C4891002 / Clinical Protocol - 1 (07Mar2023).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 30, 'activities': 44, 'marks': 216}
- C2321014 / Clinical Protocol - 1 (11Jun2024).pdf: every_visit_has_a_mark, visit_names_are_real, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 41, 'activities': 44, 'marks': 268}
- B7981080 / Clinical Protocol - 1 (12Sep2023).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 30, 'activities': 70, 'marks': 677}
- B7981032 / Clinical Protocol - 1 (15Oct2019).pdf: every_visit_has_a_mark, most_activities_are_scheduled  {'method': 'geometry', 'visits': 14, 'activities': 66, 'marks': 287}
- C4891026 / Clinical Protocol - 1 (20Nov2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 66, 'activities': 47, 'marks': 273}
- C3671013 / Clinical Protocol - 1 (23Nov2021).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 8, 'activities': 36, 'marks': 51}
- C4221026 / Clinical Protocol - 1 (25Sep2024) 7.pdf: grid_found, enough_visits_and_activities  None
- C4591076 / Clinical Protocol - 1 (26Aug2025).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 9, 'activities': 37, 'marks': 122}
- C4891006 / Clinical Protocol - 1 (27Sep2022).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 38, 'activities': 44, 'marks': 155}
- C4891023 / Clinical Protocol - 1 (27Sep2022).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 88, 'activities': 48, 'marks': 326}
- C4221016 / Clinical Protocol - 1 (31Mar2021).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 34, 'activities': 51, 'marks': 176}
- C1071005 / Clinical Protocol - 10 (19Nov2025).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 72, 'activities': 91, 'marks': 418}
- C1071003 / Clinical Protocol - 10 (22Mar2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 37, 'activities': 49, 'marks': 120}
- C4221016 / Clinical Protocol - 2 (02Dec2021).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 34, 'activities': 51, 'marks': 178}
- B7981032 / Clinical Protocol - 2 (05Feb2020).pdf: every_visit_has_a_mark, most_activities_are_scheduled  {'method': 'geometry', 'visits': 14, 'activities': 68, 'marks': 293}
- C4891026 / Clinical Protocol - 2 (11Apr2024).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 66, 'activities': 46, 'marks': 273}
- C4221015 / Clinical Protocol - 2 (12Nov2020).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 24, 'activities': 61, 'marks': 269}
- C2321014 / Clinical Protocol - 2 (13Nov2024).pdf: every_visit_has_a_mark, visit_names_are_real, every_visit_has_an_epoch, activity_names_are_label_sized, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 47, 'activities': 50, 'marks': 308}
- C4891024 / Clinical Protocol - 2 (16Jul2025).pdf: most_activities_are_scheduled  {'method': 'geometry', 'visits': 3, 'activities': 21, 'marks': 18}
- C1071006 / Clinical Protocol - 2 (16Sep2022).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 37, 'activities': 84, 'marks': 262}
- C1071004 / Clinical Protocol - 2 (17Jun2021).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 20, 'activities': 58, 'marks': 231}
- B7981080 / Clinical Protocol - 2 (17May2024).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 30, 'activities': 62, 'marks': 674}
- C3671013 / Clinical Protocol - 2 (23Mar2022).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 8, 'activities': 35, 'marks': 51}
- C4891006 / Clinical Protocol - 2 (23Nov2022).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 30, 'activities': 45, 'marks': 155}
- C4891023 / Clinical Protocol - 2 (23Nov2022).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 89, 'activities': 48, 'marks': 330}
- C4891001 / Clinical Protocol - 2 (24May2023).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 16, 'activities': 43, 'marks': 136}
- C1071007 / Clinical Protocol - 2 (28Nov2022).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 25, 'activities': 63, 'marks': 153}
- C4891002 / Clinical Protocol - 2 (28Sep2023).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 30, 'activities': 49, 'marks': 218}
- C1071005 / Clinical Protocol - 2 (29Dec2021).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 18, 'activities': 82, 'marks': 278}
- B7981080 / Clinical Protocol - 3 (01Apr2025).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 30, 'activities': 61, 'marks': 674}
- C4591048 / Clinical Protocol - 3 (01Aug2023).pdf: visit_names_are_real  {'method': 'geometry', 'visits': 30, 'activities': 37, 'marks': 289}
- C1071006 / Clinical Protocol - 3 (02Feb2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 36, 'activities': 88, 'marks': 265}
- C4891001 / Clinical Protocol - 3 (06Nov2024).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 16, 'activities': 44, 'marks': 136}
- C3671013 / Clinical Protocol - 3 (07Jul2022).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 6, 'activities': 35, 'marks': 46}
- C4221016 / Clinical Protocol - 3 (08Jun2022).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 34, 'activities': 50, 'marks': 170}
- C4891006 / Clinical Protocol - 3 (17Jul2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 65, 'activities': 63, 'marks': 305}
- C4891002 / Clinical Protocol - 3 (17Nov2025).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 7, 'activities': 17, 'marks': 35}
- C4891026 / Clinical Protocol - 3 (20Oct2025).pdf: most_activities_are_scheduled  {'method': 'geometry', 'visits': 3, 'activities': 19, 'marks': 15}
- C1071005 / Clinical Protocol - 3 (23Mar2022).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 47, 'activities': 78, 'marks': 256}
- C4221015 / Clinical Protocol - 3 (24Feb2021).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 24, 'activities': 63, 'marks': 279}
- C1071007 / Clinical Protocol - 3 (24Feb2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 25, 'activities': 63, 'marks': 153}
- C4891023 / Clinical Protocol - 3 (27Jul2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 138, 'activities': 60, 'marks': 489}
- B7981032 / Clinical Protocol - 3 (28Apr2020).pdf: every_visit_has_a_mark, most_activities_are_scheduled  {'method': 'geometry', 'visits': 14, 'activities': 68, 'marks': 293}
- C2321014 / Clinical Protocol - 3 (29Jan2025).pdf: every_visit_has_a_mark, visit_names_are_real, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 63, 'activities': 45, 'marks': 261}
- C1071004 / Clinical Protocol - 3 (29Jul2021).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 36, 'activities': 58, 'marks': 231}
- C1071005 / Clinical Protocol - 4 (01Aug2022).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 32, 'activities': 80, 'marks': 253}
- C3671013 / Clinical Protocol - 4 (08Mar2023).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 6, 'activities': 35, 'marks': 46}
- C1071004 / Clinical Protocol - 4 (09Aug2021).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 36, 'activities': 58, 'marks': 231}
- C1071006 / Clinical Protocol - 4 (13Apr2023).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 22, 'activities': 91, 'marks': 265}
- C1071007 / Clinical Protocol - 4 (14Aug2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 25, 'activities': 66, 'marks': 163}
- C4221016 / Clinical Protocol - 4 (14Feb2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 34, 'activities': 50, 'marks': 170}
- C2321014 / Clinical Protocol - 4 (27Jan2026).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 32, 'activities': 47, 'marks': 268}
- C4221015 / Clinical Protocol - 4 (28Feb2022).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 24, 'activities': 62, 'marks': 283}
- C4891023 / Clinical Protocol - 4 (28Oct2025).pdf: most_activities_are_scheduled  {'method': 'geometry', 'visits': 3, 'activities': 21, 'marks': 15}
- B7981032 / Clinical Protocol - 4 (31Aug2020).pdf: every_visit_has_a_mark, most_activities_are_scheduled  {'method': 'geometry', 'visits': 14, 'activities': 69, 'marks': 295}
- C1071006 / Clinical Protocol - 5 (01Aug2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 102, 'activities': 95, 'marks': 358}
- C4221016 / Clinical Protocol - 5 (09Oct2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 34, 'activities': 47, 'marks': 160}
- C1071007 / Clinical Protocol - 5 (10Jun2024).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 28, 'activities': 65, 'marks': 145}
- C4221015 / Clinical Protocol - 5 (20Dec2022).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 24, 'activities': 63, 'marks': 290}
- B7981032 / Clinical Protocol - 5 (23Apr2021).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 17, 'activities': 70, 'marks': 364}
- C3671013 / Clinical Protocol - 5 (31Aug2023).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 6, 'activities': 35, 'marks': 46}
- C4221015 / Clinical Protocol - 6 (13Mar2024).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 24, 'activities': 63, 'marks': 290}
- C3671013 / Clinical Protocol - 6 (19Apr2024).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 6, 'activities': 35, 'marks': 46}
- C1071007 / Clinical Protocol - 6 (19Aug2024).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 28, 'activities': 65, 'marks': 145}
- C1071005 / Clinical Protocol - 6 (21Mar2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 62, 'activities': 82, 'marks': 396}
- C1071006 / Clinical Protocol - 6 (28Feb2024).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 105, 'activities': 95, 'marks': 372}
- B7981032 / Clinical Protocol - 6 (28Mar2022).pdf: every_visit_has_a_mark, visit_names_are_real, activity_names_are_label_sized  {'method': 'geometry', 'visits': 33, 'activities': 77, 'marks': 503}
- C1071007 / Clinical Protocol - 7 (07Apr2025).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 28, 'activities': 64, 'marks': 145}
- C1071003 / Clinical Protocol - 7 (11Nov2021).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 34, 'activities': 48, 'marks': 108}
- C3671013 / Clinical Protocol - 7 (17Jun2025).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 6, 'activities': 35, 'marks': 46}
- C1071006 / Clinical Protocol - 7 (29May2024).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 153, 'activities': 94, 'marks': 373}
- C1071005 / Clinical Protocol - 7 (30Jun2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 113, 'activities': 90, 'marks': 405}
- C4221015 / Clinical Protocol - 7 (31May2024).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 24, 'activities': 63, 'marks': 290}
- C1071006 / Clinical Protocol - 8 (02Apr2025).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 193, 'activities': 91, 'marks': 365}
- C1071006 / Clinical Protocol - 8 (11Jun2025).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 170, 'activities': 98, 'marks': 385}
- C1071007 / Clinical Protocol - 8 (15Aug2025).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 28, 'activities': 64, 'marks': 145}
- C1071003 / Clinical Protocol - 8 (23Dec2021).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 20, 'activities': 48, 'marks': 116}
- C1071005 / Clinical Protocol - 8 (30Oct2023).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 127, 'activities': 83, 'marks': 256}
- C1071006 / Clinical Protocol - 9 (11Dec2025).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 163, 'activities': 101, 'marks': 404}
- C1071007 / Clinical Protocol - 9 (23Jan2026).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 44, 'activities': 64, 'marks': 150}
- C1071005 / Clinical Protocol - 9 (28Mar2025).pdf: every_visit_has_a_mark, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 72, 'activities': 91, 'marks': 418}

## Crashes

