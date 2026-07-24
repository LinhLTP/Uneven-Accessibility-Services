# Uneven Bus-Based Accessibility to Essential Opportunities in Hanoi, Vietnam

This repository contains the code required to reproduce the results and figures presented in the article **“Uneven Bus-Based Accessibility to Essential Opportunities in Hanoi, Vietnam”**, published in *Transport Findings*.

## Summary

This study analyses bus-based accessibility to nine types of essential destinations in Hanoi, Vietnam. It addresses the limited evidence on bus accessibility in Southeast Asian cities and examines: (1) how accessibility varies across space and travel-time thresholds; and (2) how unequally accessibility is distributed across the population and between urban and rural areas.

## Relative bus accessibility in Hanoi

<p align="center">
  <img src="figure/figure_1_map_rel30_all_3x3.jpeg"
       alt="Relative bus accessibility to nine types of essential opportunities in Hanoi at the 60-minute travel-time threshold"
       width="100%">
</p>

<p align="center">
  <em>Figure 1. Relative bus accessibility to nine types of essential opportunities in Hanoi at the 30-minute travel-time threshold.</em>
</p>

## Data

The study uses open-source datasets and analytical tools.

- **Public transport timetable:** The 2018 General Transit Feed Specification (GTFS) dataset was obtained from the TUMI Data Hub and validated using the Canonical GTFS Schedule Validator.
- **Opportunities and services:** Historical points of interest were retrieved from OpenStreetMap using the ohsome API.
- **Street network:** The pedestrian and road networks used in the routing analysis were obtained from OpenStreetMap.
- **Population and administrative boundaries:** Worldpop 2018 was used together with Open Mekong dataset. 

Because OpenStreetMap is continuously updated, the study used historical data corresponding to the study year wherever possible.

## Methods

### Bus accessibility

Accessibility by bus was modelled using the [`r5py`](https://r5py.readthedocs.io/stable/) package. The analysis estimated the number of opportunities reachable by public transport within specified travel-time thresholds.

### Accessibility inequality

Transport inequality was assessed from a **horizontal-equity** perspective using the Gini coefficien and Lorenz curves. Vertical equity was not assessed because reliable, fine-grained sociodemographic data were unavailable for the study area and year.
