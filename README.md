# Uneven Bus-Based Accessibility to Essential Opportunities in Hanoi, Vietnam

This repository contains the scripts required to reproduce the results and figures presented in the article **“Uneven Bus-Based Accessibility to Essential Opportunities in Hanoi, Vietnam”**, published in *Transport Findings*.

## Summary

This study analyses bus-based accessibility to nine types of essential destinations in Hanoi, Vietnam. It addresses the limited evidence on bus accessibility in Southeast Asian cities and examines: (1) how accessibility varies across space and travel-time thresholds; and (2) how unequally accessibility is distributed across the population and between urban and rural areas.

## Relative bus accessibility in Hanoi

<p align="center">
  <img src="figure/figure_1_map_rel30_all_3x3.jpeg"
       alt="Relative bus accessibility to nine types of essential opportunities in Hanoi at the 30-minute travel-time threshold"
       width="100%">
</p>

<p align="center">
  <em>Figure 1. Relative bus accessibility to nine types of essential opportunities in Hanoi at the 30-minute travel-time threshold.</em>
</p>

## Data

The study uses open-source datasets for the 2018 study year:

- **Public transport timetable:** The 2018 Hanoi General Transit Feed Specification (GTFS) timetable was obtained from the [TUMI Data Hub](https://hub.tumidata.org/en/dataset/?tags=City+of+Hanoi&res_format=GTFS). The feed was validated using the Canonical GTFS Schedule Validator.
- **Opportunities and services:** Historical points of interest were reconstructed from [OpenStreetMap](https://www.openstreetmap.org/) using the [`ohsome` R package](https://doi.org/10.32614/CRAN.package.ohsome), which provides access to the ohsome API.
- **Street network:** The pedestrian and road network used for multimodal routing was obtained from [OpenStreetMap](https://www.openstreetmap.org/).
- **Population:** Population data for 2018 were obtained from the [WorldPop Data Hub](https://hub.worldpop.org/).
- **Administrative boundaries and road data:** Administrative boundary and road datasets were obtained from [Open Development Mekong](https://data.opendevelopmentmekong.net/dataset/a-gii-hnh-chnh-vit-nam).

Because OpenStreetMap is continuously updated, historical data corresponding to the study year were used wherever possible. Some source datasets may need to be downloaded separately because of file-size limits, licensing conditions, or changes to external data services.

## Methods

### Bus accessibility

Accessibility by bus was modelled using the [`r5r` package](https://doi.org/10.32866/001c.21262). The analysis combined walking and bus travel and estimated the number of opportunities reachable within 15-, 30-, and 60-minute travel-time thresholds.

### Accessibility inequality

Transport inequality was assessed from a **horizontal-equity** perspective using population-weighted empirical cumulative distribution functions, Lorenz curves, Gini coefficients, and Theil T decomposition. Vertical equity was not assessed because reliable, fine-grained sociodemographic data were unavailable for the study area and year.
