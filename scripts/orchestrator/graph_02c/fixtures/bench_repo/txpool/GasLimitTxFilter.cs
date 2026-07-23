namespace Nethermind.TxPool.Filters {
  public class GasLimitTxFilter : ITxFilter {
    public AcceptTxResult Accept(Transaction tx, ref TxFilteringState state) {
      long gasLimit = tx.GasLimit;
      if (gasLimit > _max) { return AcceptTxResult.GasLimitExceeded; }
      return AcceptTxResult.Accepted;
    }
  }
}
