"""Static OData v4 `$metadata` CSDL document (T9).

Static, not generated from the Pydantic schemas: the service exposes a
fixed, small set of resources (`RecurringPayments`, `GetForecast`,
`Simulate` from `app/api/routes/forecast.py`; `Ask`, `Suggestions` from
`app/api/routes/assistant.py`), so hand-writing the CSDL once is simpler
and more transparent than building a schema-to-CSDL generator for a
hackathon timeline. Keep this in sync with `app/schemas/forecast.py` and
`app/schemas/assistant.py` by hand if fields change.

`RecurringPayment.recurring_id` (the entity key) doesn't exist as a
stored field - it's computed by `recurring_payment_id()` (T3) from
merchant+category+flow. The CSDL still declares it as the key property
because that's what OData clients need to address individual entities;
T10's route computes it the same way when serializing.
"""

from __future__ import annotations

METADATA_XML = """<?xml version="1.0" encoding="UTF-8"?>
<edmx:Edmx xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx" Version="4.0">
  <edmx:DataServices>
    <Schema xmlns="http://docs.oasis-open.org/odata/ns/edm" Namespace="Forecast">

      <EntityType Name="RecurringPayment">
        <Key><PropertyRef Name="recurring_id"/></Key>
        <Property Name="recurring_id" Type="Edm.String" Nullable="false"/>
        <Property Name="merchant" Type="Edm.String" Nullable="false"/>
        <Property Name="category_main" Type="Edm.String"/>
        <Property Name="category_sub" Type="Edm.String"/>
        <Property Name="amount_chf" Type="Edm.Double" Nullable="false"/>
        <Property Name="interval" Type="Edm.String" Nullable="false"/>
        <Property Name="day_of_month" Type="Edm.Int32"/>
        <Property Name="flow" Type="Edm.String" Nullable="false"/>
        <Property Name="first_seen" Type="Edm.Date" Nullable="false"/>
        <Property Name="last_seen" Type="Edm.Date" Nullable="false"/>
        <Property Name="is_active" Type="Edm.Boolean" Nullable="false"/>
      </EntityType>

      <EntityType Name="GraphNode">
        <Key><PropertyRef Name="node_id"/></Key>
        <Property Name="node_id" Type="Edm.String" Nullable="false"/>
        <Property Name="parent_id" Type="Edm.String"/>
        <Property Name="month" Type="Edm.String" Nullable="false"/>
        <Property Name="mode" Type="Edm.String" Nullable="false"/>
        <Property Name="node_type" Type="Edm.String" Nullable="false"/>
        <Property Name="level" Type="Edm.Int32" Nullable="false"/>
        <Property Name="label" Type="Edm.String" Nullable="false"/>
        <Property Name="flow" Type="Edm.String"/>
        <Property Name="amount_chf" Type="Edm.Double" Nullable="false"/>
        <Property Name="transaction_count" Type="Edm.Int32" Nullable="false"/>
        <Property Name="rank" Type="Edm.Int32"/>
        <Property Name="merchant_count" Type="Edm.Int32"/>
        <Property Name="category_main" Type="Edm.String"/>
        <Property Name="category_sub" Type="Edm.String"/>
        <Property Name="merchant" Type="Edm.String"/>
        <Property Name="has_children" Type="Edm.Boolean" Nullable="false"/>
        <Property Name="delta_baseline_median_chf" Type="Edm.Double"/>
        <Property Name="delta_diff_chf" Type="Edm.Double"/>
        <Property Name="delta_diff_pct" Type="Edm.Double"/>
        <Property Name="delta_direction" Type="Edm.String"/>
        <Property Name="summary_child_count" Type="Edm.Int32"/>
        <Property Name="summary_transaction_count" Type="Edm.Int32"/>
        <Property Name="summary_total_amount_chf" Type="Edm.Double"/>
        <Property Name="summary_avg_amount_chf" Type="Edm.Double"/>
        <Property Name="tx_id" Type="Edm.String"/>
        <Property Name="tx_date" Type="Edm.String"/>
        <Property Name="tx_value_date" Type="Edm.String"/>
        <Property Name="tx_merchant" Type="Edm.String"/>
        <Property Name="tx_merchant_canonical" Type="Edm.String"/>
        <Property Name="tx_original_description" Type="Edm.String"/>
        <Property Name="tx_amount_chf" Type="Edm.Double"/>
        <Property Name="tx_flow" Type="Edm.String"/>
        <Property Name="tx_category_main" Type="Edm.String"/>
        <Property Name="tx_category_sub" Type="Edm.String"/>
        <Property Name="tx_original_amount" Type="Edm.Double"/>
        <Property Name="tx_original_currency" Type="Edm.String"/>
        <Property Name="tx_status" Type="Edm.String"/>
      </EntityType>

      <EntityType Name="GraphMonth">
        <Key><PropertyRef Name="month"/></Key>
        <Property Name="month" Type="Edm.String" Nullable="false"/>
        <Property Name="is_default" Type="Edm.Boolean" Nullable="false"/>
        <Property Name="sort_key" Type="Edm.Int32" Nullable="false"/>
      </EntityType>

      <ComplexType Name="NextSalary">
        <Property Name="date" Type="Edm.Date"/>
        <Property Name="amount_chf" Type="Edm.Double"/>
      </ComplexType>
      <ComplexType Name="FreeToSpend">
        <Property Name="expected_chf" Type="Edm.Double"/>
        <Property Name="lower_chf" Type="Edm.Double"/>
        <Property Name="upper_chf" Type="Edm.Double"/>
      </ComplexType>
      <ComplexType Name="TightDate">
        <Property Name="date" Type="Edm.Date"/>
        <Property Name="days_until" Type="Edm.Int32"/>
        <Property Name="days_before_salary" Type="Edm.Int32"/>
        <Property Name="projected_balance_chf" Type="Edm.Double"/>
      </ComplexType>
      <ComplexType Name="KnownPayment">
        <Property Name="date" Type="Edm.Date"/>
        <Property Name="label" Type="Edm.String"/>
        <Property Name="amount_chf" Type="Edm.Double"/>
        <Property Name="category" Type="Edm.String"/>
        <Property Name="recurring_id" Type="Edm.String"/>
      </ComplexType>
      <ComplexType Name="SeriesPoint">
        <Property Name="date" Type="Edm.Date"/>
        <Property Name="expected_chf" Type="Edm.Double"/>
        <Property Name="lower_chf" Type="Edm.Double"/>
        <Property Name="upper_chf" Type="Edm.Double"/>
      </ComplexType>
      <ComplexType Name="Assumptions">
        <Property Name="variable_baseline_method" Type="Edm.String"/>
        <Property Name="band_method" Type="Edm.String"/>
        <Property Name="excluded_outliers" Type="Collection(Edm.String)"/>
        <Property Name="interest_applied" Type="Edm.Boolean"/>
        <Property Name="salary_day_detected" Type="Edm.Boolean"/>
        <Property Name="variable_baseline_months_used" Type="Edm.Int32"/>
        <Property Name="notes" Type="Collection(Edm.String)"/>
      </ComplexType>
      <ComplexType Name="ForecastResult">
        <Property Name="as_of" Type="Edm.Date"/>
        <Property Name="horizon" Type="Edm.String"/>
        <Property Name="horizon_end" Type="Edm.Date"/>
        <Property Name="opening_balance_chf" Type="Edm.Double"/>
        <Property Name="next_salary" Type="Forecast.NextSalary"/>
        <Property Name="free_to_spend" Type="Forecast.FreeToSpend"/>
        <Property Name="tight_date" Type="Forecast.TightDate"/>
        <Property Name="known_payments" Type="Collection(Forecast.KnownPayment)"/>
        <Property Name="series" Type="Collection(Forecast.SeriesPoint)"/>
        <Property Name="assumptions" Type="Forecast.Assumptions"/>
      </ComplexType>

      <ComplexType Name="DiffPoint">
        <Property Name="date" Type="Edm.Date"/>
        <Property Name="diff_chf" Type="Edm.Double"/>
      </ComplexType>
      <ComplexType Name="Diff">
        <Property Name="monthly_chf" Type="Edm.Double"/>
        <Property Name="cumulative_series" Type="Collection(Forecast.DiffPoint)"/>
        <Property Name="total_at_horizon_chf" Type="Edm.Double"/>
        <Property Name="tight_date_shift_days" Type="Edm.Int32"/>
      </ComplexType>
      <ComplexType Name="SimulateResult">
        <Property Name="baseline" Type="Forecast.ForecastResult"/>
        <Property Name="scenario" Type="Forecast.ForecastResult"/>
        <Property Name="diff" Type="Forecast.Diff"/>
      </ComplexType>

      <ComplexType Name="Adjustment">
        <Property Name="type" Type="Edm.String" Nullable="false"/>
        <Property Name="recurring_id" Type="Edm.String"/>
        <Property Name="effective_from" Type="Edm.Date"/>
        <Property Name="delta_chf" Type="Edm.Double"/>
        <Property Name="label" Type="Edm.String"/>
        <Property Name="amount_chf" Type="Edm.Double"/>
        <Property Name="interval" Type="Edm.String"/>
        <Property Name="start_date" Type="Edm.Date"/>
        <Property Name="date" Type="Edm.Date"/>
      </ComplexType>

      <!-- Assistenz (app/schemas/assistant.py). Deterministic today; the
           AI-backed extraction/phrasing steps slot in behind the same
           contract. -->
      <ComplexType Name="AssistantAssumptions">
        <Property Name="salary_growth_pct" Type="Edm.Double"/>
        <Property Name="inflation_pct" Type="Edm.Double"/>
        <Property Name="savings_rate_pct" Type="Edm.Double"/>
        <Property Name="interest_applied" Type="Edm.Boolean"/>
        <Property Name="notes" Type="Collection(Edm.String)"/>
      </ComplexType>
      <ComplexType Name="AskContext">
        <Property Name="conversation_id" Type="Edm.String"/>
        <Property Name="pending_clarification" Type="Edm.String"/>
      </ComplexType>
      <ComplexType Name="Facts">
        <Property Name="target_chf" Type="Edm.Double"/>
        <Property Name="projected_chf" Type="Edm.Double"/>
        <Property Name="gap_chf" Type="Edm.Double"/>
        <Property Name="required_monthly_chf" Type="Edm.Double"/>
        <Property Name="months_remaining" Type="Edm.Int32"/>
        <Property Name="buffer_after_months" Type="Edm.Double"/>
        <Property Name="wait_months" Type="Edm.Int32"/>
      </ComplexType>
      <ComplexType Name="Lever">
        <Property Name="category" Type="Edm.String"/>
        <Property Name="monthly_avg_chf" Type="Edm.Double"/>
        <Property Name="potential_chf" Type="Edm.Double"/>
      </ComplexType>
      <ComplexType Name="AssistantChartPoint">
        <Property Name="date" Type="Edm.String"/>
        <Property Name="expected_chf" Type="Edm.Double"/>
        <Property Name="lower_chf" Type="Edm.Double"/>
        <Property Name="upper_chf" Type="Edm.Double"/>
        <Property Name="baseline_chf" Type="Edm.Double"/>
      </ComplexType>
      <ComplexType Name="AssistantChart">
        <Property Name="type" Type="Edm.String"/>
        <Property Name="series" Type="Collection(Forecast.AssistantChartPoint)"/>
        <Property Name="target_line_chf" Type="Edm.Double"/>
        <Property Name="crossing_date" Type="Edm.String"/>
      </ComplexType>
      <ComplexType Name="Clarification">
        <Property Name="question" Type="Edm.String"/>
        <Property Name="options" Type="Collection(Edm.String)"/>
        <Property Name="field" Type="Edm.String"/>
      </ComplexType>
      <ComplexType Name="AskResult">
        <Property Name="intent" Type="Edm.String"/>
        <Property Name="status" Type="Edm.String"/>
        <Property Name="horizon" Type="Edm.String"/>
        <Property Name="answer" Type="Edm.String"/>
        <Property Name="facts" Type="Forecast.Facts"/>
        <Property Name="levers" Type="Collection(Forecast.Lever)"/>
        <Property Name="chart" Type="Forecast.AssistantChart"/>
        <Property Name="assumptions_used" Type="Forecast.AssistantAssumptions"/>
        <Property Name="clarification" Type="Forecast.Clarification"/>
        <Property Name="source" Type="Edm.String"/>
      </ComplexType>

      <Function Name="GetForecast">
        <Parameter Name="horizon" Type="Edm.String"/>
        <Parameter Name="as_of" Type="Edm.Date"/>
        <ReturnType Type="Forecast.ForecastResult"/>
      </Function>

      <Action Name="Simulate">
        <Parameter Name="horizon" Type="Edm.String"/>
        <Parameter Name="as_of" Type="Edm.Date"/>
        <Parameter Name="adjustments" Type="Collection(Forecast.Adjustment)"/>
        <ReturnType Type="Forecast.SimulateResult"/>
      </Action>

      <Action Name="Ask">
        <Parameter Name="message" Type="Edm.String" Nullable="false"/>
        <Parameter Name="horizon" Type="Edm.String"/>
        <Parameter Name="assumptions" Type="Forecast.AssistantAssumptions"/>
        <Parameter Name="context" Type="Forecast.AskContext"/>
        <ReturnType Type="Forecast.AskResult"/>
      </Action>

      <Function Name="Suggestions">
        <Parameter Name="horizon" Type="Edm.String"/>
        <ReturnType Type="Collection(Edm.String)"/>
      </Function>

      <EntityContainer Name="Container">
        <EntitySet Name="RecurringPayments" EntityType="Forecast.RecurringPayment"/>
        <EntitySet Name="GraphNodes" EntityType="Forecast.GraphNode"/>
        <EntitySet Name="GraphMonths" EntityType="Forecast.GraphMonth"/>
        <FunctionImport Name="GetForecast" Function="Forecast.GetForecast"/>
        <ActionImport Name="Simulate" Action="Forecast.Simulate"/>
        <ActionImport Name="Ask" Action="Forecast.Ask"/>
        <FunctionImport Name="Suggestions" Function="Forecast.Suggestions"/>
      </EntityContainer>

    </Schema>
  </edmx:DataServices>
</edmx:Edmx>
"""
