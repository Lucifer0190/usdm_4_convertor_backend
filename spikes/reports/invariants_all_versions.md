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
| every_visit_has_a_mark | 182/204 | 89% |
| every_visit_has_an_epoch | 172/204 | 84% |
| grid_found | 202/204 | 99% |
| marks_are_in_range | 202/204 | 99% |
| most_activities_are_scheduled | 194/204 | 95% |
| slot_found | 204/204 | 100% |
| visit_names_are_real | 199/204 | 98% |
| visit_names_are_unique_enough | 198/204 | 97% |

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
- C4221026 / Clinical Protocol - 0 (03Nov2021) 2.pdf: grid_found, enough_visits_and_activities  None
- C3671013 / Clinical Protocol - 0 (07Jul2021).pdf: every_visit_has_a_mark, every_visit_has_an_epoch  {'method': 'geometry', 'visits': 8, 'activities': 35, 'marks': 46}
- C4221016 / Clinical Protocol - 0 (13Oct2020).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 18, 'activities': 51, 'marks': 164}
- C4601003 / Clinical Protocol - 0 (14Jan2022).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 11, 'activities': 35, 'marks': 119}
- C4891001 / Clinical Protocol - 0 (15Jun2022).pdf: visit_names_are_real, every_visit_has_an_epoch  {'method': 'geometry', 'visits': 19, 'activities': 46, 'marks': 154}
- B7981118 / Clinical Protocol - 0 (16Jul2025).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 20, 'activities': 57, 'marks': 302}
- C4591048 / Clinical Protocol - 0 (19Aug2022).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 8, 'activities': 31, 'marks': 109}
- C3671058 / Clinical Protocol - 0 (19Dec2024).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 5, 'activities': 27, 'marks': 68}
- C4891024 / Clinical Protocol - 0 (22Jun2023).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 46, 'activities': 60, 'marks': 309}
- B7981119 / Clinical Protocol - 0 (28Jul2025).pdf: every_visit_has_an_epoch, visit_names_are_unique_enough  {'method': 'geometry', 'visits': 21, 'activities': 50, 'marks': 238}
- C4891024 / Clinical Protocol - 1 (02Feb2024).pdf: visit_names_are_unique_enough  {'method': 'geometry', 'visits': 46, 'activities': 60, 'marks': 309}
- B7981032 / Clinical Protocol - 1 (15Oct2019).pdf: every_visit_has_a_mark, most_activities_are_scheduled  {'method': 'geometry', 'visits': 14, 'activities': 66, 'marks': 287}
- C4601003 / Clinical Protocol - 1 (20Apr2023).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 13, 'activities': 37, 'marks': 130}
- C4591048 / Clinical Protocol - 1 (21Oct2022).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 8, 'activities': 31, 'marks': 109}
- C3671013 / Clinical Protocol - 1 (23Nov2021).pdf: every_visit_has_a_mark, every_visit_has_an_epoch  {'method': 'geometry', 'visits': 8, 'activities': 36, 'marks': 51}
- C4891001 / Clinical Protocol - 1 (25Oct2022).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 12, 'activities': 42, 'marks': 134}
- C4221026 / Clinical Protocol - 1 (25Sep2024) 7.pdf: grid_found, enough_visits_and_activities  None
- C1071005 / Clinical Protocol - 10 (19Nov2025).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 14, 'activities': 91, 'marks': 241}
- B7981032 / Clinical Protocol - 2 (05Feb2020).pdf: every_visit_has_a_mark, most_activities_are_scheduled  {'method': 'geometry', 'visits': 14, 'activities': 68, 'marks': 293}
- C2321014 / Clinical Protocol - 2 (13Nov2024).pdf: visit_names_are_real, every_visit_has_an_epoch, activity_names_are_label_sized  {'method': 'geometry', 'visits': 12, 'activities': 50, 'marks': 280}
- C4891024 / Clinical Protocol - 2 (16Jul2025).pdf: most_activities_are_scheduled  {'method': 'geometry', 'visits': 3, 'activities': 21, 'marks': 18}
- C4591048 / Clinical Protocol - 2 (18Nov2022).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 8, 'activities': 31, 'marks': 109}
- C3671013 / Clinical Protocol - 2 (23Mar2022).pdf: every_visit_has_a_mark, every_visit_has_an_epoch  {'method': 'geometry', 'visits': 8, 'activities': 35, 'marks': 51}
- C4891001 / Clinical Protocol - 2 (24May2023).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 11, 'activities': 43, 'marks': 134}
- C4601003 / Clinical Protocol - 2 (25Sep2023).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 15, 'activities': 39, 'marks': 140}
- C4591048 / Clinical Protocol - 3 (01Aug2023).pdf: visit_names_are_real, every_visit_has_an_epoch  {'method': 'geometry', 'visits': 20, 'activities': 37, 'marks': 355}
- C4891001 / Clinical Protocol - 3 (06Nov2024).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 11, 'activities': 44, 'marks': 134}
- C3671013 / Clinical Protocol - 3 (07Jul2022).pdf: every_visit_has_a_mark, every_visit_has_an_epoch  {'method': 'geometry', 'visits': 6, 'activities': 35, 'marks': 46}
- C4891026 / Clinical Protocol - 3 (20Oct2025).pdf: most_activities_are_scheduled  {'method': 'geometry', 'visits': 3, 'activities': 19, 'marks': 15}
- C4601003 / Clinical Protocol - 3 (23Apr2024).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 17, 'activities': 43, 'marks': 149}
- B7981032 / Clinical Protocol - 3 (28Apr2020).pdf: every_visit_has_a_mark, most_activities_are_scheduled  {'method': 'geometry', 'visits': 14, 'activities': 68, 'marks': 293}
- C4591048 / Clinical Protocol - 4 (01Sep2023).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 14, 'activities': 37, 'marks': 165}
- C3671013 / Clinical Protocol - 4 (08Mar2023).pdf: every_visit_has_a_mark, every_visit_has_an_epoch  {'method': 'geometry', 'visits': 6, 'activities': 35, 'marks': 46}
- C4891001 / Clinical Protocol - 4 (15Jan2026).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 11, 'activities': 43, 'marks': 134}
- C4601003 / Clinical Protocol - 4 (28Aug2025).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 17, 'activities': 45, 'marks': 151}
- C4891023 / Clinical Protocol - 4 (28Oct2025).pdf: most_activities_are_scheduled  {'method': 'geometry', 'visits': 3, 'activities': 21, 'marks': 15}
- B7981032 / Clinical Protocol - 4 (31Aug2020).pdf: every_visit_has_a_mark, most_activities_are_scheduled  {'method': 'geometry', 'visits': 14, 'activities': 69, 'marks': 295}
- C4591048 / Clinical Protocol - 5 (05Jul2024).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 14, 'activities': 34, 'marks': 151}
- C4221016 / Clinical Protocol - 5 (09Oct2023).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 20, 'activities': 47, 'marks': 160}
- C4601003 / Clinical Protocol - 5 (11Nov2025).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 17, 'activities': 45, 'marks': 151}
- B7981032 / Clinical Protocol - 5 (23Apr2021).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 14, 'activities': 70, 'marks': 358}
- C3671013 / Clinical Protocol - 5 (31Aug2023).pdf: every_visit_has_a_mark, every_visit_has_an_epoch  {'method': 'geometry', 'visits': 6, 'activities': 35, 'marks': 46}
- C4591048 / Clinical Protocol - 6 (03Oct2024).pdf: every_visit_has_an_epoch  {'method': 'geometry', 'visits': 14, 'activities': 34, 'marks': 151}
- C3671013 / Clinical Protocol - 6 (19Apr2024).pdf: every_visit_has_a_mark, every_visit_has_an_epoch  {'method': 'geometry', 'visits': 6, 'activities': 35, 'marks': 46}
- B7981032 / Clinical Protocol - 6 (28Mar2022).pdf: every_visit_has_a_mark, activity_names_are_label_sized  {'method': 'geometry', 'visits': 14, 'activities': 73, 'marks': 379}
- C3671013 / Clinical Protocol - 7 (17Jun2025).pdf: every_visit_has_a_mark, every_visit_has_an_epoch  {'method': 'geometry', 'visits': 6, 'activities': 35, 'marks': 46}
- C1071005 / Clinical Protocol - 7 (30Jun2023).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 14, 'activities': 90, 'marks': 225}
- C1071005 / Clinical Protocol - 8 (30Oct2023).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 15, 'activities': 83, 'marks': 216}
- C1071005 / Clinical Protocol - 9 (28Mar2025).pdf: every_visit_has_a_mark  {'method': 'geometry', 'visits': 14, 'activities': 91, 'marks': 241}

## Crashes

